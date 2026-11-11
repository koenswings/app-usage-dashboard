#!/usr/bin/env python3
"""verify_service_tar.py — check that saved service image tars match their compose pins (idea#445).

Read-only and Docker-free: it opens each tar with Python's tarfile module and reads
index.json, manifest.json and the blobs it needs. It never extracts to disk, never
runs docker, and never writes anything.

Called by script/verify-service-tar.sh. See docs/packaging.md "Verify a service tar".

Tar naming follows agent-engine-dev main src/data/ImageRef.ts:
    saveName(ref)            repo:tag (digest stripped; a digest without a tag is an error)
    serviceImageTarName(ref) saveName(ref) with every '/' -> '_' plus '.tar'
e.g. ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:... ->
     ghcr.io_koenswings_usage-dashboard-web:1.0.tar

Layouts (what the top-level entry in the tar's index.json is):
  index     an OCI image index / Docker manifest list. Its digest must equal the pin,
            and the linux/arm64 manifest, its config and its layers must be in the tar.
  manifest  a single image manifest (no index above it in the tar).
            * digest == pin: the image has no index (single-platform image pinned by
              its manifest digest, e.g. ef48f1fa). Pass. This matches the Engine's
              idea#322 checkLoadedDigest (RepoDigests carry repo@<manifest digest>).
            * digest != pin: the tar holds only a platform manifest while the pin is
              something else (typically the index). FAIL by default: after a load,
              repo:tag@<index> does not resolve offline and the Engine refuses the
              start. Accepted only with --platform-digest equal to the tar's manifest
              digest, which is flagged as a warning (see docs; pending Axle's #445
              rule for offline USB disks).

Exit codes: 0 all checked tars pass; 1 at least one check failed (including a
missing tar); 2 usage or compose errors.
"""
import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
INDEX_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}
MANIFEST_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
ENGINE_PLATFORM = ("linux", "arm64")


class UsageError(Exception):
    pass


# --- ImageRef.ts equivalents -------------------------------------------------

def parse_image_ref(ref):
    r = ref.strip()
    rest, digest = r, None
    at = r.find("@")
    if at != -1:
        digest = r[at + 1:]
        rest = r[:at]
        if not DIGEST_RE.match(digest):
            raise UsageError("image reference %s: '%s' is not a sha256 digest" % (ref, digest))
    slash = rest.rfind("/")
    colon = rest.rfind(":")
    repo, tag = rest, None
    if colon > slash:
        repo, tag = rest[:colon], rest[colon + 1:]
    if not repo:
        raise UsageError("image reference %s has no repository" % ref)
    return {"ref": r, "repo": repo, "tag": tag, "digest": digest}


def save_name(ref):
    p = parse_image_ref(ref)
    if p["tag"]:
        return "%s:%s" % (p["repo"], p["tag"])
    if p["digest"]:
        raise UsageError(
            "image reference %s pins a digest without a tag: use repo:tag@%s (idea#322)" % (ref, p["digest"])
        )
    return p["repo"]


def service_image_tar_name(ref):
    return save_name(ref).replace("/", "_") + ".tar"


def legacy_service_image_tar_name(ref):
    return ref.strip().replace("/", "_") + ".tar"


def norm_name(name):
    """docker.io/library/x:t, docker.io/x:t and x:t compare equal (Engine normRepo)."""
    n = name.strip()
    for prefix in ("docker.io/", "index.docker.io/"):
        if n.startswith(prefix):
            n = n[len(prefix):]
    if n.startswith("library/"):
        n = n[len("library/"):]
    return n


# --- compose -----------------------------------------------------------------

def compose_services(path):
    """(service, image) pairs under top-level services:. Same shape the e2e awk reads."""
    out = []
    in_services = False
    current = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if raw.strip().startswith("#") or not raw.strip():
            continue
        if not raw.startswith(" "):
            in_services = raw.rstrip() == "services:"
            current = None
            continue
        if not in_services:
            continue
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", raw)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"^    image:\s*(\S+)", raw)
        if m and current:
            out.append((current, m.group(1).strip("\"'")))
    return out


# --- tar reading -------------------------------------------------------------

class TarView:
    def __init__(self, path):
        self.path = path
        self.tf = tarfile.open(path, "r:*")
        self.members = {}
        for m in self.tf.getmembers():
            name = m.name[2:] if m.name.startswith("./") else m.name
            self.members[name] = m

    def close(self):
        self.tf.close()

    def has(self, name):
        m = self.members.get(name)
        return m is not None and m.isfile()

    def read(self, name):
        m = self.members.get(name)
        if m is None or not m.isfile():
            return None
        fh = self.tf.extractfile(m)
        return fh.read() if fh else None

    def json(self, name):
        data = self.read(name)
        if data is None:
            return None
        return json.loads(data.decode("utf-8"))

    def blob_name(self, digest):
        return "blobs/sha256/" + digest.split(":", 1)[1]

    def blob_sha256(self, digest):
        m = self.members.get(self.blob_name(digest))
        if m is None or not m.isfile():
            return None, None
        h = hashlib.sha256()
        fh = self.tf.extractfile(m)
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
        return "sha256:" + h.hexdigest(), m.size


def entry_name(entry):
    ann = entry.get("annotations") or {}
    name = ann.get("io.containerd.image.name")
    if name:
        return name
    ref = ann.get("org.opencontainers.image.ref.name")
    if ref and ("/" in ref or ":" in ref):
        return ref
    return None


def verify_tar(tar_path, ref, platform_digest=None):
    """Return (ok, layout, messages). messages is a list of (level, text)."""
    msgs = []
    p = parse_image_ref(ref)
    if not p["digest"]:
        raise UsageError("%s is not digest-pinned; nothing to verify" % ref)
    pin = p["digest"]
    want_name = save_name(ref)
    if not Path(tar_path).is_file():
        return False, None, [("FAIL", "tar not found: %s" % tar_path)]
    try:
        tv = TarView(tar_path)
    except (tarfile.TarError, OSError) as exc:
        return False, None, [("FAIL", "cannot read %s as a tar: %s" % (tar_path, exc))]
    try:
        return _verify_open(tv, ref, pin, want_name, platform_digest, msgs)
    finally:
        tv.close()


def _verify_open(tv, ref, pin, want_name, platform_digest, msgs):
    try:
        index = tv.json("index.json")
        manifest = tv.json("manifest.json")
    except (ValueError, UnicodeDecodeError) as exc:
        return False, None, [("FAIL", "index.json or manifest.json is not valid JSON: %s" % exc)]
    if index is None:
        return False, None, [("FAIL", "no index.json (classic pre-OCI docker save layout); cannot tell which digest it holds")]
    if manifest is None:
        return False, None, [("FAIL", "no manifest.json; not a docker save tar")]

    entries = [e for e in (index.get("manifests") or []) if isinstance(e, dict)]
    if not entries:
        return False, None, [("FAIL", "index.json lists no manifests")]

    # Name check, index.json side.
    named = [e for e in entries if entry_name(e) and norm_name(entry_name(e)) == norm_name(want_name)]
    names_seen = sorted({entry_name(e) for e in entries if entry_name(e)})
    if not named:
        if len(entries) == 1 and entry_name(entries[0]) is None:
            named = entries  # unnamed single entry; manifest.json must name it below
            msgs.append(("INFO", "index.json entry has no name annotation; relying on manifest.json RepoTags"))
        else:
            return False, None, [("FAIL", "image name mismatch: index.json names %s, expected %s"
                                  % (", ".join(names_seen) or "(none)", want_name))]
    digests = sorted({e.get("digest") for e in named})
    if len(digests) > 1:
        return False, None, [("FAIL", "%d index.json entries named %s with different digests (%s); ambiguous"
                              % (len(named), want_name, ", ".join(digests)))]
    if len(entries) > 1:
        msgs.append(("INFO", "index.json has %d entries (%s); checking the one named %s"
                     % (len(entries), ", ".join(names_seen) or "unnamed", want_name)))
    top = named[0]

    # Name check, manifest.json side.
    tags = []
    for item in manifest if isinstance(manifest, list) else []:
        tags.extend((item or {}).get("RepoTags") or [])
    if not any(norm_name(t) == norm_name(want_name) for t in tags):
        return False, None, [("FAIL", "image name mismatch: manifest.json RepoTags %s, expected %s"
                              % (", ".join(tags) or "(none)", want_name))]

    top_digest = top.get("digest") or ""
    if not DIGEST_RE.match(top_digest):
        return False, None, [("FAIL", "index.json entry has no sha256 digest: %r" % top_digest)]

    # Top-level blob must be present and hash to its digest.
    got, size = tv.blob_sha256(top_digest)
    if got is None:
        return False, None, [("FAIL", "top-level blob %s is not in the tar" % top_digest)]
    if got != top_digest:
        return False, None, [("FAIL", "top-level blob for %s hashes to %s (corrupt tar)" % (top_digest, got))]
    if top.get("size") is not None and int(top["size"]) != size:
        return False, None, [("FAIL", "top-level blob %s size %s, index.json says %s" % (top_digest, size, top["size"]))]
    try:
        top_doc = json.loads(tv.read(tv.blob_name(top_digest)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False, None, [("FAIL", "top-level blob %s is not JSON" % top_digest)]
    media = top.get("mediaType") or top_doc.get("mediaType") or ""
    if media not in INDEX_TYPES and media not in MANIFEST_TYPES:
        media = "application/vnd.oci.image.index.v1+json" if "manifests" in top_doc else (
            "application/vnd.oci.image.manifest.v1+json" if "config" in top_doc else media)

    if media in INDEX_TYPES:
        layout = "index"
        if top_digest != pin:
            return False, layout, msgs + [("FAIL", "digest mismatch: tar index is %s, compose pins %s" % (top_digest, pin))]
        plat = [m for m in (top_doc.get("manifests") or [])
                if ((m.get("platform") or {}).get("os"), (m.get("platform") or {}).get("architecture")) == ENGINE_PLATFORM]
        if not plat:
            return False, layout, msgs + [("FAIL", "index %s lists no linux/arm64 manifest" % pin)]
        pm = plat[0]["digest"]
        ok, why = _check_manifest_content(tv, pm)
        if not ok:
            return False, layout, msgs + [("FAIL", "index %s: linux/arm64 manifest %s: %s; the tar would not load offline" % (pin, pm, why))]
        msgs.append(("INFO", "layout=index digest=%s linux/arm64=%s" % (top_digest, pm)))
        return True, layout, msgs

    if media in MANIFEST_TYPES:
        layout = "manifest"
        ok, why = _check_manifest_content(tv, top_digest, verified=True)
        if not ok:
            return False, layout, msgs + [("FAIL", "manifest %s: %s" % (top_digest, why))]
        if top_digest == pin:
            msgs.append(("INFO", "layout=manifest digest=%s (single-platform image, no index; pin is its manifest digest)" % top_digest))
            return True, layout, msgs
        if platform_digest and platform_digest == top_digest:
            msgs.append(("WARN", "layout=manifest: tar holds only platform manifest %s, compose pins %s. "
                         "Accepted because --platform-digest matches. The idea#322 Engine check refuses "
                         "this tar at start (repo:tag@<pin> does not resolve offline); see docs/packaging.md "
                         "and Axle's idea#445 rule." % (top_digest, pin)))
            return True, layout, msgs
        hint = ""
        if platform_digest:
            hint = " (--platform-digest %s does not match it either)" % platform_digest
        return False, layout, msgs + [("FAIL", "platform-manifest only: tar top-level entry is manifest %s, compose pins %s%s. "
                                       "A `docker save --platform` or a classic-store save writes this layout; re-export "
                                       "with script/publish-web-image.sh --export-tar" % (top_digest, pin, hint))]

    return False, None, msgs + [("FAIL", "unknown top-level media type %r" % media)]


def _check_manifest_content(tv, digest, verified=False):
    if not verified:
        got, _ = tv.blob_sha256(digest)
        if got is None:
            return False, "blob not in the tar"
        if got != digest:
            return False, "blob hashes to %s" % got
    try:
        doc = json.loads(tv.read(tv.blob_name(digest)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return False, "blob is not JSON"
    cfg = (doc.get("config") or {}).get("digest")
    if not cfg or not tv.has(tv.blob_name(cfg)):
        return False, "config blob %s missing" % cfg
    missing = [l.get("digest") for l in (doc.get("layers") or []) if not tv.has(tv.blob_name(l.get("digest") or "sha256:x"))]
    if missing:
        return False, "%d layer blob(s) missing (first %s)" % (len(missing), missing[0])
    try:
        conf = json.loads(tv.read(tv.blob_name(cfg)).decode("utf-8"))
        osarch = (conf.get("os"), conf.get("architecture"))
        if all(osarch) and osarch != ENGINE_PLATFORM:
            return False, "config platform is %s/%s, the Engine needs linux/arm64" % osarch
    except (ValueError, UnicodeDecodeError):
        pass
    return True, ""


# --- CLI ---------------------------------------------------------------------

def report(label, ok, msgs, out):
    for level, text in msgs:
        if level == "FAIL":
            continue
        print("  %s %s" % (level, text), file=out)
    status = "PASS" if ok else "FAIL"
    fails = [t for lvl, t in msgs if lvl == "FAIL"]
    print("%s %s%s" % (status, label, (": " + "; ".join(fails)) if fails else ""), file=out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify-service-tar.sh",
        description="Check that saved service image tars match their compose digest pins (idea#445). Read-only, no Docker.",
    )
    ap.add_argument("compose", nargs="?", help="compose.yaml")
    ap.add_argument("services_dir", nargs="?", help="services/ directory (e.g. /services)")
    ap.add_argument("--tar", help="check this one tar file instead of a services dir (needs --image)")
    ap.add_argument("--image", help="the pinned ref the --tar must match (repo:tag@sha256:...)")
    ap.add_argument("--service", action="append", default=[], help="only check these compose services")
    ap.add_argument("--platform-digest", help="accept a platform-manifest-only tar whose manifest digest is this (flagged WARN)")
    ap.add_argument("--print-tar-name", metavar="REF", help="print serviceImageTarName(REF) and exit")
    ap.add_argument("--print-save-name", metavar="REF", help="print saveName(REF) (repo:tag) and exit")
    args = ap.parse_args(argv)

    try:
        if args.print_save_name:
            print(save_name(args.print_save_name))
            return 0
        if args.print_tar_name:
            print(service_image_tar_name(args.print_tar_name))
            return 0
        if args.platform_digest and not DIGEST_RE.match(args.platform_digest):
            raise UsageError("--platform-digest must be sha256:<64 hex>")
        if args.tar:
            if not args.image or args.compose or args.services_dir:
                raise UsageError("--tar needs --image and no compose/services-dir arguments")
            ok, _, msgs = verify_tar(args.tar, args.image, args.platform_digest)
            report("%s (%s)" % (args.tar, args.image), ok, msgs, sys.stdout)
            return 0 if ok else 1
        if not args.compose or not args.services_dir:
            raise UsageError("usage: verify-service-tar.sh <compose.yaml> <services-dir> | --tar FILE --image REF")
        if not Path(args.compose).is_file():
            raise UsageError("compose file not found: %s" % args.compose)
        services = compose_services(args.compose)
        if not services:
            raise UsageError("no services with an image: in %s" % args.compose)
        known = {s for s, _ in services}
        for s in args.service:
            if s not in known:
                raise UsageError("unknown service %s (compose has %s)" % (s, ", ".join(sorted(known))))
        sdir = Path(args.services_dir)
        checked = failed = 0
        for svc, ref in services:
            if args.service and svc not in args.service:
                continue
            if "@" not in ref:
                print("SKIP %s %s: not digest-pinned" % (svc, ref))
                continue
            tar_path = sdir / service_image_tar_name(ref)
            legacy = sdir / legacy_service_image_tar_name(ref)
            checked += 1
            ok, _, msgs = verify_tar(str(tar_path), ref, args.platform_digest)
            if not tar_path.is_file() and legacy.is_file():
                msgs.append(("FAIL", "only the pre-#322 digest-named tar %s exists; it loads without a name" % legacy.name))
            report("%s %s -> %s" % (svc, ref, tar_path), ok, msgs, sys.stdout)
            if not ok:
                failed += 1
        print("summary: %d checked, %d passed, %d failed" % (checked, checked - failed, failed))
        return 1 if failed else 0
    except UsageError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
