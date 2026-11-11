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

The verdict mirrors the Engine's pre-load check exactly: agent-engine-dev PR #327
(tip 1f9ff92) src/data/ImageRef.ts checkServiceTarPin (l.217-287). The "named
entry" is the index.json descriptor whose io.containerd.image.name (or a repo-like
org.opencontainers.image.ref.name) equals repo:tag; manifest.json RepoTags must
name repo:tag too.

  MATCH       (a) named image index, digest == pin                        (l.277-278)
              (a') bare index.json that is itself an image index whose
                   bytes hash to the pin, with no name annotation         (l.242-245)
              (b) named single manifest, digest == pin (one-platform
                   image with no index, e.g. the old ef48f1fa)            (l.281-282)
  MISMATCH    (a) named image index, digest != pin                        (l.279)
              (c) platform-manifest-only entry, digest != pin. Always
                   refused (Steve, idea#445): after docker load,
                   repo:tag@<index> does not resolve offline.             (l.283-284)
              The Engine quarantines a MISMATCH tar.
  UNREADABLE  (d) no index.json / manifest.json or not JSON, no entries,
                   name not found, duplicate name on different digests,
                   no digest, missing or corrupt top-level blob, unknown
                   media type                                             (l.224-268, 286)
              The Engine does not quarantine an UNREADABLE tar.
  MISSING     no tar under serviceImageTarName (Engine state 'missing').

Exit codes (the worst state wins, in this order): 1 a MISMATCH, 3 an UNREADABLE,
4 a MISSING tar, 0 all MATCH; 2 usage or compose errors.
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


def entry_name(entry):
    ann = entry.get("annotations") or {}
    name = ann.get("io.containerd.image.name")
    if name:
        return name
    ref = ann.get("org.opencontainers.image.ref.name")
    if ref and ("/" in ref or ":" in ref):
        return ref
    return None


MATCH, MISMATCH, UNREADABLE, MISSING = "MATCH", "MISMATCH", "UNREADABLE", "MISSING"
EXIT = {MISMATCH: 1, UNREADABLE: 3, MISSING: 4}


def norm_image_name(name):
    """ImageRef.ts normImageName: parse, normRepo(repo), keep :tag."""
    try:
        p = parse_image_ref(name)
    except UsageError:
        return name.strip()
    return "%s:%s" % (norm_name(p["repo"]), p["tag"]) if p["tag"] else norm_name(p["repo"])


def verify_tar(tar_path, ref):
    """Return (state, digest, layout, reason); state is MATCH/MISMATCH/UNREADABLE/MISSING."""
    p = parse_image_ref(ref)
    if not p["digest"]:
        raise UsageError("%s is not digest-pinned; nothing to verify" % ref)
    if not Path(tar_path).is_file():
        return MISSING, None, None, "tar not found: %s" % tar_path
    try:
        tv = TarView(tar_path)
    except (tarfile.TarError, OSError) as exc:
        return UNREADABLE, None, None, "cannot read %s as a tar: %s" % (tar_path, exc)
    try:
        return check_service_tar_pin(ref, tv)
    finally:
        tv.close()


def _json(data):
    try:
        return json.loads(data.decode("utf-8")), True
    except (ValueError, UnicodeDecodeError):
        return None, False


def check_service_tar_pin(ref, tv):
    """Line-for-line port of checkServiceTarPin (agent-engine-dev #327 ImageRef.ts:217)."""
    p = parse_image_ref(ref)
    pin = p["digest"]
    want = save_name(ref)

    index_bytes = tv.read("index.json")
    if index_bytes is None:
        return UNREADABLE, None, None, "no index.json"
    index, ok = _json(index_bytes)
    if not ok:
        return UNREADABLE, None, None, "index.json is not JSON"

    manifest_bytes = tv.read("manifest.json")
    if manifest_bytes is None:
        return UNREADABLE, None, None, "no manifest.json"
    manifest, ok = _json(manifest_bytes)
    if not ok:
        return UNREADABLE, None, None, "manifest.json is not JSON"

    raw = index.get("manifests") if isinstance(index, dict) else None
    entries = [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []
    if not entries:
        return UNREADABLE, None, None, "index.json lists no manifests"

    named = [e for e in entries if entry_name(e) is not None and norm_image_name(entry_name(e)) == norm_image_name(want)]
    chosen = named
    if not named:
        # (a) extra: index.json itself is the image index and hashes to the pin.
        file_digest = "sha256:" + hashlib.sha256(index_bytes).hexdigest()
        if file_digest == pin and (index.get("mediaType") in INDEX_TYPES or any(e.get("platform") for e in entries)):
            return MATCH, file_digest, "index", "bare index.json is the pinned image index"
        if len(entries) == 1 and entry_name(entries[0]) is None:
            chosen = entries
        else:
            return UNREADABLE, None, None, "image name mismatch: index.json does not name %s" % want
    digests = sorted({e.get("digest") for e in chosen if isinstance(e.get("digest"), str) and DIGEST_RE.match(e.get("digest"))})
    if len(digests) > 1:
        return UNREADABLE, None, None, "duplicate name %s with different digests (%s)" % (want, ", ".join(digests))
    top = chosen[0]
    top_digest = top.get("digest")
    if not (isinstance(top_digest, str) and DIGEST_RE.match(top_digest)):
        return UNREADABLE, None, None, "index.json entry has no sha256 digest"

    tags = []
    if isinstance(manifest, list):
        for item in manifest:
            if isinstance(item, dict):
                tags.extend(str(t) for t in (item.get("RepoTags") or []))
    if not any(norm_image_name(t) == norm_image_name(want) for t in tags):
        return UNREADABLE, top_digest, None, "image name mismatch: manifest.json RepoTags do not include %s" % want

    blob = tv.read(tv.blob_name(top_digest))
    if blob is None:
        return UNREADABLE, top_digest, None, "top-level blob %s is not in the tar" % top_digest
    got = "sha256:" + hashlib.sha256(blob).hexdigest()
    if got != top_digest:
        return UNREADABLE, top_digest, None, "top-level blob %s hashes to %s" % (top_digest, got)

    media = top.get("mediaType") if isinstance(top.get("mediaType"), str) else ""
    if media not in INDEX_TYPES and media not in MANIFEST_TYPES:
        doc, ok = _json(blob)
        if ok and isinstance(doc, dict):
            if isinstance(doc.get("manifests"), list):
                media = "application/vnd.oci.image.index.v1+json"
            elif doc.get("config"):
                media = "application/vnd.oci.image.manifest.v1+json"
    if media in INDEX_TYPES:
        if top_digest == pin:
            return MATCH, top_digest, "index", "named image index equals the pin"
        return MISMATCH, top_digest, "index", "tar index is %s, compose pins %s" % (top_digest, pin)
    if media in MANIFEST_TYPES:
        if top_digest == pin:
            return MATCH, top_digest, "manifest", "named single manifest equals the pin (no index)"
        # (c) refused, no override (Steve, idea#445)
        return MISMATCH, top_digest, "manifest", ("platform-manifest only: tar top-level entry is manifest %s, compose pins %s. "
                                                  "Re-export with script/publish-web-image.sh --export-tar" % (top_digest, pin))
    return UNREADABLE, top_digest, None, "unknown top-level media type %s" % (media or "(none)")


# --- CLI ---------------------------------------------------------------------

def report(label, state, digest, layout, reason, out):
    detail = []
    if layout:
        detail.append("layout=%s" % layout)
    if digest:
        detail.append("digest=%s" % digest)
    print("%s %s%s%s" % (state, label, (" " + " ".join(detail)) if detail else "", (": " + reason) if reason else ""), file=out)


def worst(states):
    for s in (MISMATCH, UNREADABLE, MISSING):
        if s in states:
            return EXIT[s]
    return 0


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
        if args.tar:
            if not args.image or args.compose or args.services_dir:
                raise UsageError("--tar needs --image and no compose/services-dir arguments")
            state, digest, layout, reason = verify_tar(args.tar, args.image)
            report("%s (%s)" % (args.tar, args.image), state, digest, layout, reason, sys.stdout)
            return worst([state])
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
        states = []
        for svc, ref in services:
            if args.service and svc not in args.service:
                continue
            if "@" not in ref:
                print("SKIP %s %s: not digest-pinned" % (svc, ref))
                continue
            tar_path = sdir / service_image_tar_name(ref)
            state, digest, layout, reason = verify_tar(str(tar_path), ref)
            legacy = sdir / legacy_service_image_tar_name(ref)
            if state == MISSING and legacy.is_file():
                reason += "; only the pre-#322 digest-named tar %s exists (it loads without a name)" % legacy.name
            report("%s %s -> %s" % (svc, ref, tar_path), state, digest, layout, reason, sys.stdout)
            states.append(state)
        counts = {k: states.count(k) for k in (MATCH, MISMATCH, UNREADABLE, MISSING)}
        print("summary: %d checked, %d match, %d mismatch, %d unreadable, %d missing"
              % (len(states), counts[MATCH], counts[MISMATCH], counts[UNREADABLE], counts[MISSING]))
        return worst(states)
    except UsageError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
