"""idea#445: script/verify-service-tar.sh (verify_service_tar.py) on fixture tars.

Every row of the Engine's checkServiceTarPin (agent-engine-dev #327 tip 1f9ff92,
src/data/ImageRef.ts:217-287) has a test here; the verdicts must stay identical.

Fixture tars are built in temp dirs with the same layout a containerd-store
`docker save repo:tag` writes: oci-layout, index.json (top-level entry named with
io.containerd.image.name), manifest.json (RepoTags) and blobs/sha256/<hex>.
tests/fixtures/web-9b5501f0/ holds the byte-exact published index, linux/arm64
manifest and config of ghcr.io/koenswings/usage-dashboard-web@sha256:9b5501f0 (from
`crane manifest` / `crane blob`), so the real pin is checked too; its layer blobs are
stand-ins (only their names are checked).
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "script" / "verify-service-tar.sh"
FIX = Path(__file__).resolve().parent / "fixtures" / "web-9b5501f0"
sys.path.insert(0, str(REPO / "script"))
import verify_service_tar as v  # noqa: E402

OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
WEB = "ghcr.io/koenswings/usage-dashboard-web"
REAL_PIN = "sha256:9b5501f0690f02146217595f177496612d107aefd2bd56c181f84c7f1c678139"


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def jbytes(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


class Image:
    """One image's blobs: layers, config, a linux/arm64 manifest, optionally an index."""

    def __init__(self, seed: str, arch="arm64", with_index=True):
        self.blobs = {}
        layer = ("layer-" + seed).encode() * 50
        self.layer = self.add(layer)
        config = jbytes({"architecture": arch, "os": "linux", "rootfs": {"type": "layers", "diff_ids": [self.layer]}})
        self.config = self.add(config)
        manifest = jbytes({
            "schemaVersion": 2, "mediaType": OCI_MANIFEST,
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": self.config, "size": len(config)},
            "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": self.layer, "size": len(layer)}],
        })
        self.manifest = self.add(manifest)
        self.manifest_size = len(manifest)
        self.index = None
        if with_index:
            att = jbytes({"schemaVersion": 2, "mediaType": OCI_MANIFEST, "attestation": seed})
            att_d = self.add(att)
            index = jbytes({
                "schemaVersion": 2, "mediaType": OCI_INDEX,
                "manifests": [
                    {"mediaType": OCI_MANIFEST, "digest": self.manifest, "size": len(manifest),
                     "platform": {"architecture": arch, "os": "linux"}},
                    {"mediaType": OCI_MANIFEST, "digest": att_d, "size": len(att),
                     "annotations": {"vnd.docker.reference.digest": self.manifest, "vnd.docker.reference.type": "attestation-manifest"},
                     "platform": {"architecture": "unknown", "os": "unknown"}},
                ],
            })
            self.index = self.add(index)
            self.index_size = len(index)

    def add(self, data: bytes) -> str:
        d = sha(data)
        self.blobs[d] = data
        return d

    def entry(self, name, top="index"):
        if top == "index":
            digest, media, size = self.index, OCI_INDEX, self.index_size
        else:
            digest, media, size = self.manifest, OCI_MANIFEST, self.manifest_size
        ann = {"io.containerd.image.name": name, "org.opencontainers.image.ref.name": name.rsplit(":", 1)[-1]} if name else {}
        e = {"mediaType": media, "digest": digest, "size": size}
        if ann:
            e["annotations"] = ann
        return e


def write_tar(path, entries, images, repo_tags, drop=(), extra=None, no_index=False):
    blobs = {}
    for img in images:
        blobs.update(img.blobs)
    for d in drop:
        blobs.pop(d, None)
    files = {"oci-layout": jbytes({"imageLayoutVersion": "1.0.0"})}
    if not no_index:
        files["index.json"] = jbytes({"schemaVersion": 2, "mediaType": OCI_INDEX, "manifests": entries})
    files["manifest.json"] = jbytes([{"Config": "blobs/sha256/x", "RepoTags": repo_tags, "Layers": []}])
    for d, data in blobs.items():
        files["blobs/sha256/" + d.split(":", 1)[1]] = data
    files.update(extra or {})
    with tarfile.open(path, "w") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def compose_text(web_ref, extra_services=""):
    return """x-app:
  name: usage-dashboard
  version: "1.0"
services:
  collector:
    image: python:3.12-slim-bookworm
  web:
    image: %s
    labels:
      x-app-version: "1.0"
%s""" % (web_ref, extra_services)


class TarNamingTests(unittest.TestCase):
    """Mirrors agent-engine-dev main src/data/ImageRef.ts saveName / serviceImageTarName."""

    def test_pinned_ghcr_ref_maps_to_repo_tag_tar(self):
        ref = "%s:1.0@%s" % (WEB, REAL_PIN)
        self.assertEqual(v.save_name(ref), WEB + ":1.0")
        self.assertEqual(v.service_image_tar_name(ref), "ghcr.io_koenswings_usage-dashboard-web:1.0.tar")

    def test_official_and_tag_only_refs(self):
        self.assertEqual(v.service_image_tar_name("python:3.12-slim-bookworm@sha256:" + "a" * 64), "python:3.12-slim-bookworm.tar")
        self.assertEqual(v.service_image_tar_name("tailscale/tailscale:v1.88.3"), "tailscale_tailscale:v1.88.3.tar")
        self.assertEqual(v.service_image_tar_name("traefik/whoami:v1"), "traefik_whoami:v1.tar")
        self.assertEqual(v.service_image_tar_name("localhost:5000/x/y:2@sha256:" + "b" * 64), "localhost:5000_x_y:2.tar")

    def test_digest_without_tag_is_refused(self):
        with self.assertRaises(v.UsageError):
            v.save_name(WEB + "@" + REAL_PIN)

    def test_docker_io_names_normalise(self):
        self.assertEqual(v.norm_name("docker.io/library/python:3.12"), v.norm_name("python:3.12"))


class VerifyTarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.img = Image("one")
        self.name = WEB + ":1.0"
        self.ref = "%s@%s" % (self.name, self.img.index)

    def tearDown(self):
        self.tmp.cleanup()

    def tar(self, *a, **kw):
        return write_tar(str(self.dir / "t.tar"), *a, **kw)

    def raw_tar(self, files):
        path = str(self.dir / "raw.tar")
        with tarfile.open(path, "w") as tf:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        return path

    def run_cli(self, *args):
        return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, cwd=str(REPO))

    def assertState(self, tar, ref, state, layout=None, reason=None, code=None):
        got, digest, got_layout, why = v.verify_tar(tar, ref)
        self.assertEqual(got, state, why)
        if layout is not None:
            self.assertEqual(got_layout, layout)
        if reason is not None:
            self.assertIn(reason, why or "")
        if code is not None:
            r = self.run_cli("--tar", tar, "--image", ref)
            self.assertEqual(r.returncode, code, r.stdout + r.stderr)
            self.assertTrue(r.stdout.startswith(state + " "), r.stdout)
        return digest

    # --- (a) named image index: ImageRef.ts:277-279 ---

    def test_a_named_index_equal_to_pin_matches(self):
        t = self.tar([self.img.entry(self.name)], [self.img], [self.name])
        self.assertState(t, self.ref, v.MATCH, layout="index", code=0)

    def test_a_named_index_not_equal_to_pin_is_mismatch(self):
        other = Image("two")
        t = self.tar([other.entry(self.name)], [other], [self.name])
        d = self.assertState(t, self.ref, v.MISMATCH, layout="index", code=1)
        self.assertEqual(d, other.index)

    def test_a_atlas_real_layout_for_9b5501f0_matches(self):
        """The layout Atlas reads on idea03: an OCI index entry for 9b5501f0 named
        with io.containerd.image.name, plus manifest.json RepoTags."""
        index = (FIX / "index.json").read_bytes()
        manifest = (FIX / "arm64-manifest.json").read_bytes()
        config = (FIX / "config.json").read_bytes()
        self.assertEqual(sha(index), REAL_PIN)
        files = {"oci-layout": jbytes({"imageLayoutVersion": "1.0.0"})}
        for data in (index, manifest, config):
            files["blobs/sha256/" + sha(data).split(":", 1)[1]] = data
        files["index.json"] = jbytes({"schemaVersion": 2, "mediaType": OCI_INDEX, "manifests": [{
            "mediaType": OCI_INDEX, "digest": REAL_PIN, "size": len(index),
            "annotations": {"io.containerd.image.name": self.name, "org.opencontainers.image.ref.name": "1.0"}}]})
        files["manifest.json"] = jbytes([{"Config": "blobs/sha256/" + sha(config).split(":", 1)[1],
                                          "RepoTags": [self.name], "Layers": []}])
        t = self.raw_tar(files)
        ref = "%s@%s" % (self.name, REAL_PIN)
        self.assertState(t, ref, v.MATCH, layout="index", code=0)
        # Historical 1.0 pin fixture; 1.2 compose uses a different digest.

    # --- (a) extra: bare image-index index.json hashing to the pin: ImageRef.ts:242-245 ---

    def test_a_extra_bare_index_json_hashing_to_pin_matches(self):
        index = (FIX / "index.json").read_bytes()  # the published 9b5501f0 index, no name annotations
        t = self.raw_tar({"index.json": index, "manifest.json": jbytes([{"RepoTags": []}])})
        self.assertState(t, "%s@%s" % (self.name, REAL_PIN), v.MATCH, layout="index", reason="bare index.json", code=0)

    def test_a_extra_bare_index_json_with_other_digest_is_unreadable(self):
        index = (FIX / "index.json").read_bytes()
        t = self.raw_tar({"index.json": index, "manifest.json": jbytes([{"RepoTags": []}])})
        self.assertState(t, self.ref, v.UNREADABLE, reason="does not name", code=3)

    # --- (b) named single manifest: ImageRef.ts:281-282 ---

    def test_b_named_single_manifest_equal_to_pin_matches(self):
        single = Image("single", with_index=False)
        ref = "%s@%s" % (self.name, single.manifest)
        t = self.tar([single.entry(self.name, top="manifest")], [single], [self.name])
        self.assertState(t, ref, v.MATCH, layout="manifest", code=0)

    # --- (c) platform-manifest-only, other pin: ImageRef.ts:283-284, always refused ---

    def test_c_platform_manifest_only_is_mismatch(self):
        t = self.tar([self.img.entry(self.name, top="manifest")], [self.img], [self.name], drop=[self.img.index])
        d = self.assertState(t, self.ref, v.MISMATCH, layout="manifest", reason="platform-manifest only", code=1)
        self.assertEqual(d, self.img.manifest)

    def test_c_stale_ef48_style_tar_against_new_pin_is_mismatch(self):
        """The idea03 case: a single-manifest tar of the old pin, compose now pins a new index."""
        old = Image("old", with_index=False)
        t = self.tar([old.entry(self.name, top="manifest")], [old], [self.name])
        self.assertState(t, self.ref, v.MISMATCH, layout="manifest", code=1)

    def test_c_has_no_platform_digest_escape_hatch(self):
        t = self.tar([self.img.entry(self.name, top="manifest")], [self.img], [self.name], drop=[self.img.index])
        r = self.run_cli("--tar", t, "--image", self.ref, "--platform-digest", self.img.manifest)
        self.assertEqual(r.returncode, 2)  # unknown option
        src = (REPO / "script" / "verify_service_tar.py").read_text(encoding="utf-8")
        self.assertNotIn("platform_digest", src)
        self.assertNotIn("WARN", src)

    # --- (d) unreadable: ImageRef.ts:219-268, 286 ---

    def _base_files(self):
        files = {"index.json": jbytes({"schemaVersion": 2, "manifests": [self.img.entry(self.name)]}),
                 "manifest.json": jbytes([{"RepoTags": [self.name]}])}
        for d, data in self.img.blobs.items():
            files["blobs/sha256/" + d.split(":", 1)[1]] = data
        return files

    def test_d_unreadable_rows(self):
        cases = {
            "no index.json": lambda f: f.pop("index.json"),
            "index.json is not JSON": lambda f: f.__setitem__("index.json", b"{nope"),
            "no manifest.json": lambda f: f.pop("manifest.json"),
            "manifest.json is not JSON": lambda f: f.__setitem__("manifest.json", b"[nope"),
            "index.json lists no manifests": lambda f: f.__setitem__("index.json", jbytes({"manifests": []})),
            "index.json does not name": lambda f: f.__setitem__("index.json", jbytes({"manifests": [self.img.entry(WEB + ":0.9")]})),
            "manifest.json RepoTags do not include": lambda f: f.__setitem__("manifest.json", jbytes([{"RepoTags": ["usage-dashboard-web:local-abc"]}])),
            "is not in the tar": lambda f: f.pop("blobs/sha256/" + self.img.index.split(":", 1)[1]),
            "hashes to": lambda f: f.__setitem__("blobs/sha256/" + self.img.index.split(":", 1)[1], b"{}"),
            "has no sha256 digest": lambda f: f.__setitem__("index.json", jbytes({"manifests": [
                {"mediaType": OCI_INDEX, "digest": "md5:x", "annotations": {"io.containerd.image.name": self.name}}]})),
        }
        for reason, mutate in cases.items():
            with self.subTest(reason=reason):
                files = self._base_files()
                mutate(files)
                self.assertState(self.raw_tar(files), self.ref, v.UNREADABLE, reason=reason, code=3)

    def test_d_duplicate_name_on_different_digests_is_unreadable(self):
        other = Image("two")
        t = self.tar([other.entry(self.name), self.img.entry(self.name)], [other, self.img], [self.name])
        self.assertState(t, self.ref, v.UNREADABLE, reason="duplicate name", code=3)

    def test_d_unknown_media_type_is_unreadable(self):
        junk = jbytes({"neither": "index nor manifest"})
        d = sha(junk)
        files = {"index.json": jbytes({"manifests": [{"digest": d, "annotations": {"io.containerd.image.name": self.name}}]}),
                 "manifest.json": jbytes([{"RepoTags": [self.name]}]),
                 "blobs/sha256/" + d.split(":", 1)[1]: junk}
        self.assertState(self.raw_tar(files), self.ref, v.UNREADABLE, reason="unknown top-level media type", code=3)

    def test_d_not_a_tar_is_unreadable(self):
        path = self.dir / "junk.tar"
        path.write_bytes(b"not a tar at all")
        self.assertState(str(path), self.ref, v.UNREADABLE, code=3)

    # --- naming details shared with the Engine ---

    def test_unnamed_single_entry_relies_on_manifest_json(self):
        t = self.tar([self.img.entry(None)], [self.img], [self.name])
        self.assertState(t, self.ref, v.MATCH, layout="index")

    def test_repo_like_oci_ref_name_counts_as_the_name(self):
        e = self.img.entry(None)
        e["annotations"] = {"org.opencontainers.image.ref.name": self.name}
        other = Image("x")
        t = self.tar([other.entry(WEB + ":0.9"), e], [other, self.img], [self.name])
        self.assertState(t, self.ref, v.MATCH)
        # A bare tag-only ref.name ("1.0") is not a name.
        e["annotations"] = {"org.opencontainers.image.ref.name": "1.0"}
        t = self.tar([other.entry(WEB + ":0.9"), e], [other, self.img], [self.name])
        self.assertState(t, self.ref, v.UNREADABLE, reason="does not name")

    def test_multi_manifest_tar_checks_the_named_entry(self):
        other = Image("python")
        entries = [other.entry("docker.io/library/python:3.12-slim-bookworm"), self.img.entry(self.name)]
        t = self.tar(entries, [other, self.img], ["python:3.12-slim-bookworm", self.name])
        self.assertState(t, self.ref, v.MATCH)
        self.assertState(t, "python:3.12-slim-bookworm@" + other.index, v.MATCH)

    # --- services-dir mode, exit codes ---

    def _compose(self, ref):
        compose = self.dir / "compose.yaml"
        compose.write_text(compose_text(ref), encoding="utf-8")
        sdir = self.dir / "services"
        sdir.mkdir(exist_ok=True)
        return compose, sdir

    def test_missing_tar_exit_4(self):
        compose, sdir = self._compose(self.ref)
        r = self.run_cli(str(compose), str(sdir))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("MISSING web", r.stdout)
        self.assertIn("ghcr.io_koenswings_usage-dashboard-web:1.0.tar", r.stdout)
        self.assertIn("SKIP collector python:3.12-slim-bookworm: not digest-pinned", r.stdout)
        self.assertIn("summary: 1 checked, 0 match, 0 mismatch, 0 unreadable, 1 missing", r.stdout)

    def test_services_dir_match_exit_0(self):
        compose, sdir = self._compose(self.ref)
        write_tar(str(sdir / "ghcr.io_koenswings_usage-dashboard-web:1.0.tar"), [self.img.entry(self.name)], [self.img], [self.name])
        r = self.run_cli(str(compose), str(sdir))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("summary: 1 checked, 1 match, 0 mismatch, 0 unreadable, 0 missing", r.stdout)

    def test_worst_state_wins(self):
        self.assertEqual(v.worst([v.MATCH, v.MISSING, v.UNREADABLE, v.MISMATCH]), 1)
        self.assertEqual(v.worst([v.MATCH, v.MISSING, v.UNREADABLE]), 3)
        self.assertEqual(v.worst([v.MATCH, v.MISSING]), 4)
        self.assertEqual(v.worst([v.MATCH]), 0)

    def test_legacy_digest_named_tar_is_called_out(self):
        compose, sdir = self._compose(self.ref)
        write_tar(str(sdir / v.legacy_service_image_tar_name(self.ref)), [self.img.entry(self.name)], [self.img], [self.name])
        r = self.run_cli(str(compose), str(sdir))
        self.assertEqual(r.returncode, 4)
        self.assertIn("pre-#322 digest-named tar", r.stdout)

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("--tar", "x.tar").returncode, 2)
        self.assertEqual(self.run_cli("--tar", "x.tar", "--image", self.name).returncode, 2)  # not pinned
        self.assertEqual(self.run_cli(str(self.dir / "missing.yaml"), str(self.dir)).returncode, 2)
        r = self.run_cli("--print-tar-name", "%s:1.0@%s" % (WEB, REAL_PIN))
        self.assertEqual(r.stdout.strip(), "ghcr.io_koenswings_usage-dashboard-web:1.0.tar")

    def test_script_is_read_only_and_docker_free(self):
        src = (REPO / "script" / "verify_service_tar.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", src)
        self.assertNotIn("extractall", src)
        self.assertNotIn(".extract(", src)
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
