import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "script" / "check-compose.mjs"
COMPOSE = REPO / "compose.yaml"
EXAMPLE = REPO / "compose.web-ghcr.example.yaml"
NGINX = REPO / "web" / "nginx.conf"


class PackagingTests(unittest.TestCase):
    def _check(self, *args):
        return subprocess.run(
            ["node", str(CHECK), *args],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )

    def test_check_compose_passes_default(self):
        result = self._check(str(COMPOSE))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("ok", result.stdout)

    def test_release_check_passes_on_pinned_compose(self):
        result = self._check("--release", str(COMPOSE))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("ok", result.stdout)

    def test_release_check_fails_on_placeholder(self):
        result = self._check("--release", str(EXAMPLE))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stderr + result.stdout
        self.assertIn("placeholder", combined.lower())

    def test_release_check_passes_filled_in_ghcr_pin(self):
        digest = "a" * 64
        body = """x-app:
  name: usage-dashboard
  version: "1.0"
services:
  tailscale:
    image: tailscale/tailscale:v1.88.3
    labels:
      x-app-version: "1.0"
  collector:
    image: python:3.12-slim-bookworm
    labels:
      x-app-version: "1.0"
  web:
    image: ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:%s
    labels:
      x-app-version: "1.0"
    restart: unless-stopped
""" % digest
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            result = self._check("--release", "--tag", "1.0", path)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        finally:
            Path(path).unlink()

    def test_release_check_also_accepts_version_shortsha_pin(self):
        digest = "a" * 64
        body = """x-app:
  name: usage-dashboard
  version: "1.0"
services:
  tailscale:
    image: tailscale/tailscale:v1.88.3
    labels:
      x-app-version: "1.0"
  collector:
    image: python:3.12-slim-bookworm
    labels:
      x-app-version: "1.0"
  web:
    image: ghcr.io/koenswings/usage-dashboard-web:1.0-0d929618656e@sha256:%s
    labels:
      x-app-version: "1.0"
    restart: unless-stopped
""" % digest
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            result = self._check("--release", "--tag", "1.0", path)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        finally:
            Path(path).unlink()

    def test_pin_web_digest_rewrites_local_build(self):
        digest = "b" * 64
        tmpdir = Path(tempfile.mkdtemp())
        dest = tmpdir / "compose.yaml"
        dest.write_text(COMPOSE.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run(
            [
                "bash",
                str(REPO / "script" / "pin-web-digest.sh"),
                "--compose",
                str(dest),
                "--digest",
                "sha256:" + digest,
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        rewritten = dest.read_text(encoding="utf-8")
        self.assertIn(
            "image: ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:" + digest,
            rewritten,
        )
        collected = []
        capturing = False
        for line in rewritten.splitlines():
            if line == "  web:":
                capturing = True
                collected = [line]
                continue
            if capturing:
                if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":") and not line.startswith("   "):
                    if line.split(":", 1)[0].strip() and not line.startswith("    "):
                        break
                if line and not line[0] in " \t":
                    break
                collected.append(line)
        web_block = "\n".join(collected)
        self.assertTrue(web_block.startswith("  web:"), rewritten)
        self.assertNotIn("build:", web_block)
        self.assertNotIn("pull_policy: never", web_block)
        result = self._check("--release", "--tag", "1.0", str(dest))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        dest.unlink()
        tmpdir.rmdir()


    def test_check_compose_requires_matching_state_dir(self):
        body = COMPOSE.read_text(encoding="utf-8").replace(
            "- TS_STATE_DIR=/var/lib/tailscale",
            "- TS_STATE_DIR=/tmp/not-the-mount",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            result = self._check(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TS_STATE_DIR", result.stderr + result.stdout)
        finally:
            Path(path).unlink()

    def test_check_compose_requires_auth_once(self):
        body = COMPOSE.read_text(encoding="utf-8").replace(
            "- TS_AUTH_ONCE=true",
            "- TS_AUTH_ONCE=false",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            result = self._check(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TS_AUTH_ONCE", result.stderr + result.stdout)
        finally:
            Path(path).unlink()

    def test_backup_exclude_covers_keys_and_sidecar_dirs(self):
        """x-app.backup.exclude must list keys, node state, and the socket dir."""
        text = COMPOSE.read_text(encoding="utf-8")
        start = text.index("  backup:")
        rest = text[start:]
        # Stop at the next top-level or services: block.
        end_candidates = [rest.find("\nservices:"), rest.find("\n  services:")]
        end = min(i for i in end_candidates if i != -1)
        block = rest[:end]
        names = re.findall(r"^\s+- ([^\s#]+)", block, flags=re.M)
        self.assertEqual(
            names,
            ["keys", "tailscale", "tailscale-run"],
            "x-app.backup.exclude must be keys, tailscale (node state) and tailscale-run (socket dir); got %r\n%s" % (names, block),
        )

    def test_nginx_assets_return_404_and_spa_fallback_remains(self):
        text = NGINX.read_text(encoding="utf-8")
        assets = re.search(
            r"location /assets/ \{.*?\}",
            text,
            flags=re.S,
        )
        self.assertIsNotNone(assets, text)
        self.assertIn("try_files $uri =404;", assets.group(0))
        root = re.search(
            r"location / \{.*?\}",
            text,
            flags=re.S,
        )
        self.assertIsNotNone(root, text)
        self.assertIn("try_files $uri /index.html;", root.group(0))

    # --- idea#445 -----------------------------------------------------------

    def _pin(self, *args):
        digest = "b" * 64
        tmpdir = Path(tempfile.mkdtemp())
        dest = tmpdir / "compose.yaml"
        dest.write_text(COMPOSE.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run(
            ["bash", str(REPO / "script" / "pin-web-digest.sh"), "--compose", str(dest),
             "--digest", "sha256:" + digest, *args],
            capture_output=True, text=True, cwd=str(REPO),
        )
        return result, digest, tmpdir, dest

    def test_pin_web_digest_prints_pin_change_runbook(self):
        result, digest, tmpdir, dest = self._pin()
        try:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            out = result.stdout
            self.assertIn("Pin-change runbook (idea#445", out)
            steps = [
                "mv <services>/ghcr.io_koenswings_usage-dashboard-web:1.0.tar /home/pi/kid-quarantine/",
                "script/publish-web-image.sh --export-tar <services> --pin ghcr.io/koenswings/usage-dashboard-web:1.0@sha256:" + digest,
                "script/verify-service-tar.sh compose.yaml <services>",
                "docker tag ghcr.io/koenswings/usage-dashboard-web@sha256:%s ghcr.io/koenswings/usage-dashboard-web:1.0" % digest,
                "Engine-driven start",
            ]
            positions = [out.index(step) for step in steps]
            self.assertEqual(positions, sorted(positions), out)
        finally:
            dest.unlink()
            tmpdir.rmdir()

    def test_pin_web_digest_check_only_also_prints_runbook(self):
        result = subprocess.run(
            ["bash", str(REPO / "script" / "pin-web-digest.sh"), "--check-only", "--digest", "sha256:" + "c" * 64],
            capture_output=True, text=True, cwd=str(REPO),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("Pin-change runbook", result.stdout)

    def test_pin_web_digest_services_dir_runs_verify(self):
        with tempfile.TemporaryDirectory() as sdir:
            result, digest, tmpdir, dest = self._pin("--services-dir", sdir)
            try:
                # No tar there yet: the verify step must fail and say why.
                self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
                self.assertIn("tar not found", result.stdout)
                self.assertIn("ghcr.io_koenswings_usage-dashboard-web:1.0.tar", result.stdout)
            finally:
                dest.unlink()
                tmpdir.rmdir()

    def test_no_script_tags_a_local_build_with_a_published_name(self):
        """Local builds are :local-<sha> only; published tags appear only on the --push path."""
        pub = (REPO / "script" / "publish-web-image.sh").read_text(encoding="utf-8")
        self.assertIn('"${LOCAL_REPO}:local-${short}"', pub)
        push_branch = pub[pub.index('if [ "$PUSH" = 1 ]; then\n    echo "image:'):pub.index("  else\n    # Local test build")]
        self.assertIn('--tag "$IMAGE"', push_branch)
        self.assertIn("--push", push_branch)
        self.assertEqual(pub.count('--tag "$IMAGE"'), 1)
        e2e = (REPO / "script" / "e2e-tar-fallback.sh").read_text(encoding="utf-8")
        self.assertNotIn("docker build", e2e)
        self.assertNotIn("buildx build", e2e)
        docs = (REPO / "docs" / "packaging.md").read_text(encoding="utf-8")
        self.assertNotIn("-t ghcr.io/koenswings/usage-dashboard-web", docs)
        self.assertIn(":local-<shortsha>", docs)

    def test_packaging_docs_cover_idea445(self):
        docs = (REPO / "docs" / "packaging.md").read_text(encoding="utf-8")
        for needle in (
            "## Pin-change runbook",
            "script/verify-service-tar.sh",
            "--export-tar",
            "--platform-digest",
            "layout=index",
            "layout=manifest",
        ):
            self.assertIn(needle, docs)

    def test_source_stays_out_of_docs_and_docs_out_of_script(self):
        self.assertEqual(sorted(p.suffix for p in (REPO / "docs").iterdir()), [".md"] * len(list((REPO / "docs").iterdir())))
        self.assertEqual([p.name for p in (REPO / "script").iterdir() if p.suffix == ".md"], [])


if __name__ == "__main__":
    unittest.main()
