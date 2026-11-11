"""idea#445: publish-web-image.sh --export-tar and local test-build tags, with a stub docker.

The stub records every docker call, writes buildx metadata, and answers
`docker save` with a fixture tar, so no Docker daemon or registry is used.
"""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PUBLISH = REPO / "script" / "publish-web-image.sh"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_verify_service_tar import Image, write_tar, WEB  # noqa: E402

STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FAKE_LOG"
case "$1 ${2:-}" in
  "buildx version") exit 0 ;;
  "buildx build")
    while [ $# -gt 0 ]; do
      if [ "$1" = "--metadata-file" ]; then printf '{"containerimage.digest": "%s"}' "$FAKE_DIGEST" > "$2"; fi
      shift
    done
    exit 0 ;;
  "image pull"|"image tag") exit 0 ;;
esac
if [ "$1" = save ]; then cat "$FAKE_TAR"; exit 0; fi
echo "stub docker: unexpected $*" >&2; exit 9
"""

NAME = WEB + ":1.0"
TARNAME = "ghcr.io_koenswings_usage-dashboard-web:1.0.tar"


class PublishExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.stub = self.dir / "docker"
        self.stub.write_text(STUB, encoding="utf-8")
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IXUSR)
        self.log = self.dir / "docker.log"
        self.out = self.dir / "services"
        self.out.mkdir()
        self.img = Image("pub")
        self.pin = "%s@%s" % (NAME, self.img.index)
        self.good = write_tar(str(self.dir / "good.tar"), [self.img.entry(NAME)], [self.img], [NAME])
        self.short = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "--short=12", "HEAD"], text=True).strip()

    def tearDown(self):
        self.tmp.cleanup()

    def run_pub(self, *args, tar=None, digest=None):
        env = dict(os.environ, DOCKER=str(self.stub), FAKE_LOG=str(self.log),
                   FAKE_TAR=tar or self.good, FAKE_DIGEST=digest or self.img.index)
        return subprocess.run(["bash", str(PUBLISH), *args], capture_output=True, text=True, cwd=str(REPO), env=env)

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_export_matches_engine_steps_and_renames(self):
        r = self.run_pub("--export-tar", str(self.out), "--pin", self.pin)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.out / TARNAME).is_file())
        self.assertFalse((self.out / (TARNAME + ".partial")).exists())
        calls = self.calls()
        self.assertEqual(calls, [
            "image pull --platform linux/arm64 " + self.pin,
            "image tag %s %s" % (self.pin, NAME),
            "save " + NAME,
        ])
        self.assertNotIn("build", " ".join(calls))
        self.assertIn("export: ok", r.stdout)

    def test_export_of_mismatched_tar_is_not_renamed(self):
        other = Image("other")
        bad = write_tar(str(self.dir / "bad.tar"), [other.entry(NAME)], [other], [NAME])
        r = self.run_pub("--export-tar", str(self.out), "--pin", self.pin, tar=bad)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse((self.out / TARNAME).exists())
        self.assertTrue((self.out / (TARNAME + ".partial")).is_file())
        self.assertIn("MISMATCH ", r.stdout)
        self.assertIn("not renamed", r.stderr)

    def test_existing_matching_tar_is_left_alone(self):
        dest = self.out / TARNAME
        dest.write_bytes(Path(self.good).read_bytes())
        r = self.run_pub("--export-tar", str(self.out), "--pin", self.pin)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("already matches the pin", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_existing_stale_tar_stops_the_export(self):
        old = Image("old", with_index=False)
        dest = self.out / TARNAME
        write_tar(str(dest), [old.entry(NAME, top="manifest")], [old], [NAME])
        before = dest.read_bytes()
        r = self.run_pub("--export-tar", str(self.out), "--pin", self.pin)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Quarantine it first", r.stderr)
        self.assertEqual(dest.read_bytes(), before)
        self.assertEqual(self.calls(), [])

    def test_export_defaults_to_the_compose_pin(self):
        compose_pin = None
        for line in (REPO / "compose.yaml").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("image: " + WEB):
                compose_pin = line.split("image:", 1)[1].strip()
        r = self.run_pub("--export-tar", str(self.out))
        # The stub tar is not the real image, so verify fails, but the pull used the compose pin.
        self.assertIn("image pull --platform linux/arm64 " + compose_pin, self.calls())
        self.assertNotEqual(r.returncode, 0)

    def test_local_build_uses_local_tag_only(self):
        r = self.run_pub()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        build = [c for c in self.calls() if c.startswith("buildx build")]
        self.assertEqual(len(build), 1, self.calls())
        self.assertIn("--tag usage-dashboard-web:local-" + self.short, build[0])
        self.assertNotIn("ghcr.io", build[0])
        self.assertNotIn("--push", build[0])
        self.assertIn("not a pin", r.stdout)

    def test_push_then_export_uses_the_new_digest(self):
        r = self.run_pub("--push", "--export-tar", str(self.out))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        build = [c for c in self.calls() if c.startswith("buildx build")][0]
        self.assertIn("--tag %s --tag %s-%s" % (NAME, NAME, self.short), build)
        self.assertIn("--push", build)
        self.assertIn("pin:    " + self.pin, r.stdout)
        self.assertIn("image pull --platform linux/arm64 " + self.pin, self.calls())
        self.assertTrue((self.out / TARNAME).is_file())

    def test_flag_combinations(self):
        self.assertNotEqual(self.run_pub("--pin", self.pin).returncode, 0)
        self.assertNotEqual(self.run_pub("--push", "--export-tar", str(self.out), "--pin", self.pin).returncode, 0)
        r = self.run_pub("--export-tar", str(self.out), "--pin", NAME)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("digest pin", r.stderr)


if __name__ == "__main__":
    unittest.main()
