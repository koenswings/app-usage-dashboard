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

    def test_release_check_fails_while_web_is_local_build(self):
        result = self._check("--release", str(COMPOSE))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage-dashboard-web:1.0", result.stderr)
        self.assertIn("build:", result.stderr)

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


if __name__ == "__main__":
    unittest.main()
