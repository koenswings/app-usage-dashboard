"""idea#445: script/verify-service-tar.sh (verify_service_tar.py) on fixture tars.

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

    def run_cli(self, *args):
        return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, cwd=str(REPO))

    # --- index layout ---

    def test_matching_index_tar_passes(self):
        t = self.tar([self.img.entry(self.name)], [self.img], [self.name])
        ok, layout, msgs = v.verify_tar(t, self.ref)
        self.assertTrue(ok, msgs)
        self.assertEqual(layout, "index")
        r = self.run_cli("--tar", t, "--image", self.ref)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS", r.stdout)
        self.assertIn("layout=index", r.stdout)

    def test_wrong_digest_fails(self):
        other = Image("two")
        t = self.tar([other.entry(self.name)], [other], [self.name])
        ok, layout, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("digest mismatch", " ".join(m for _, m in msgs))
        r = self.run_cli("--tar", t, "--image", self.ref)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)
        self.assertIn(other.index, r.stdout)
        self.assertIn(self.img.index, r.stdout)

    def test_stale_ef48_style_tar_against_new_pin_fails(self):
        """The idea03 case: a single-manifest tar of the old pin, compose now pins a new index."""
        old = Image("old", with_index=False)
        t = self.tar([old.entry(self.name, top="manifest")], [old], [self.name])
        ok, layout, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertEqual(layout, "manifest")
        self.assertIn("platform-manifest only", " ".join(m for _, m in msgs))

    def test_wrong_name_in_index_fails(self):
        t = self.tar([self.img.entry(WEB + ":0.9")], [self.img], [WEB + ":0.9"])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("image name mismatch", " ".join(m for _, m in msgs))

    def test_wrong_name_in_manifest_json_fails(self):
        t = self.tar([self.img.entry(self.name)], [self.img], ["usage-dashboard-web:local-abc"])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("manifest.json RepoTags", " ".join(m for _, m in msgs))

    def test_missing_tar_fails_with_exit_1(self):
        sdir = self.dir / "services"
        sdir.mkdir()
        compose = self.dir / "compose.yaml"
        compose.write_text(compose_text(self.ref), encoding="utf-8")
        r = self.run_cli(str(compose), str(sdir))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("tar not found", r.stdout)
        self.assertIn("ghcr.io_koenswings_usage-dashboard-web:1.0.tar", r.stdout)
        self.assertIn("SKIP collector python:3.12-slim-bookworm: not digest-pinned", r.stdout)
        self.assertIn("summary: 1 checked, 0 passed, 1 failed", r.stdout)

    def test_services_dir_pass(self):
        sdir = self.dir / "services"
        sdir.mkdir()
        write_tar(str(sdir / "ghcr.io_koenswings_usage-dashboard-web:1.0.tar"), [self.img.entry(self.name)], [self.img], [self.name])
        compose = self.dir / "compose.yaml"
        compose.write_text(compose_text(self.ref), encoding="utf-8")
        r = self.run_cli(str(compose), str(sdir))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("summary: 1 checked, 1 passed, 0 failed", r.stdout)

    def test_legacy_digest_named_tar_is_called_out(self):
        sdir = self.dir / "services"
        sdir.mkdir()
        write_tar(str(sdir / v.legacy_service_image_tar_name(self.ref)), [self.img.entry(self.name)], [self.img], [self.name])
        compose = self.dir / "compose.yaml"
        compose.write_text(compose_text(self.ref), encoding="utf-8")
        r = self.run_cli(str(compose), str(sdir))
        self.assertEqual(r.returncode, 1)
        self.assertIn("pre-#322 digest-named tar", r.stdout)

    def test_multi_manifest_tar_checks_the_named_entry(self):
        other = Image("python")
        entries = [other.entry("docker.io/library/python:3.12-slim-bookworm"), self.img.entry(self.name)]
        t = self.tar(entries, [other, self.img], ["python:3.12-slim-bookworm", self.name])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertTrue(ok, msgs)
        self.assertIn("index.json has 2 entries", " ".join(m for _, m in msgs))
        # The other image in the same tar is found by its normalised docker.io name.
        ok2, _, msgs2 = v.verify_tar(t, "python:3.12-slim-bookworm@" + other.index)
        self.assertTrue(ok2, msgs2)

    def test_multi_manifest_tar_same_name_two_digests_is_ambiguous(self):
        other = Image("two")
        entries = [other.entry(self.name), self.img.entry(self.name)]
        t = self.tar(entries, [other, self.img], [self.name])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("ambiguous", " ".join(m for _, m in msgs))

    def test_index_without_arm64_content_fails(self):
        t = self.tar([self.img.entry(self.name)], [self.img], [self.name], drop=[self.img.layer])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("would not load offline", " ".join(m for _, m in msgs))
        t = self.tar([self.img.entry(self.name)], [self.img], [self.name], drop=[self.img.manifest])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("blob not in the tar", " ".join(m for _, m in msgs))

    def test_amd64_only_index_fails(self):
        amd = Image("amd", arch="amd64")
        ref = "%s@%s" % (self.name, amd.index)
        t = self.tar([amd.entry(self.name)], [amd], [self.name])
        ok, _, msgs = v.verify_tar(t, ref)
        self.assertFalse(ok)
        self.assertIn("no linux/arm64 manifest", " ".join(m for _, m in msgs))

    def test_corrupt_top_level_blob_fails(self):
        bad = {"blobs/sha256/" + self.img.index.split(":", 1)[1]: b"{}"}
        t = self.tar([self.img.entry(self.name)], [self.img], [self.name], extra=bad)
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("corrupt", " ".join(m for _, m in msgs))

    def test_classic_layout_without_index_json_fails(self):
        t = self.tar([], [self.img], [self.name], no_index=True)
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertIn("no index.json", " ".join(m for _, m in msgs))

    def test_unnamed_single_entry_relies_on_manifest_json(self):
        t = self.tar([self.img.entry(None)], [self.img], [self.name])
        ok, _, msgs = v.verify_tar(t, self.ref)
        self.assertTrue(ok, msgs)

    # --- manifest-only layout ---

    def test_single_platform_image_pinned_by_manifest_passes(self):
        single = Image("single", with_index=False)
        ref = "%s@%s" % (self.name, single.manifest)
        t = self.tar([single.entry(self.name, top="manifest")], [single], [self.name])
        ok, layout, msgs = v.verify_tar(t, ref)
        self.assertTrue(ok, msgs)
        self.assertEqual(layout, "manifest")

    def test_platform_manifest_only_tar_fails_by_default(self):
        # Same image, but the tar only carries the arm64 manifest (docker save --platform).
        t = self.tar([self.img.entry(self.name, top="manifest")], [self.img], [self.name], drop=[self.img.index])
        ok, layout, msgs = v.verify_tar(t, self.ref)
        self.assertFalse(ok)
        self.assertEqual(layout, "manifest")
        r = self.run_cli("--tar", t, "--image", self.ref)
        self.assertEqual(r.returncode, 1)
        self.assertIn("platform-manifest only", r.stdout)
        self.assertIn("--export-tar", r.stdout)

    def test_platform_manifest_only_tar_accepted_with_matching_platform_digest(self):
        t = self.tar([self.img.entry(self.name, top="manifest")], [self.img], [self.name], drop=[self.img.index])
        r = self.run_cli("--tar", t, "--image", self.ref, "--platform-digest", self.img.manifest)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARN", r.stdout)
        self.assertIn("refuses", r.stdout)
        r = self.run_cli("--tar", t, "--image", self.ref, "--platform-digest", "sha256:" + "c" * 64)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not match it either", r.stdout)

    # --- the real published pin ---

    def test_real_9b5501f0_index_layout_passes(self):
        index = (FIX / "index.json").read_bytes()
        manifest = (FIX / "arm64-manifest.json").read_bytes()
        config = (FIX / "config.json").read_bytes()
        self.assertEqual(sha(index), REAL_PIN)
        files = {}
        for data in (index, manifest, config):
            files["blobs/sha256/" + sha(data).split(":", 1)[1]] = data
        for layer in json.loads(manifest)["layers"]:
            files["blobs/sha256/" + layer["digest"].split(":", 1)[1]] = b"stand-in"
        entry = {"mediaType": OCI_INDEX, "digest": REAL_PIN, "size": len(index),
                 "annotations": {"io.containerd.image.name": self.name, "org.opencontainers.image.ref.name": "1.0"}}
        t = write_tar(str(self.dir / "real.tar"), [entry], [], [self.name], extra=files)
        ref = "%s@%s" % (self.name, REAL_PIN)
        ok, layout, msgs = v.verify_tar(t, ref)
        self.assertTrue(ok, msgs)
        self.assertEqual(layout, "index")
        # And the compose pin on this branch is that digest.
        self.assertIn(ref, (REPO / "compose.yaml").read_text(encoding="utf-8"))

    # --- usage ---

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
