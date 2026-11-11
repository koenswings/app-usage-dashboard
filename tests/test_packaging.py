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

    def _backup_block(self):
        text = COMPOSE.read_text(encoding="utf-8")
        start = text.index("  backup:")
        rest = text[start:]
        # Stop at the next top-level or services: block.
        end_candidates = [rest.find("\nservices:"), rest.find("\n  services:")]
        end = min(i for i in end_candidates if i != -1)
        return rest[:end]

    def _list_under(self, block, key):
        header = re.search(r"(?m)^    %s:\s*$" % re.escape(key), block)
        self.assertIsNotNone(header, "missing %s in\n%s" % (key, block))
        rest = block[header.end():]
        items = []
        for line in rest.splitlines():
            if re.match(r"^    [A-Za-z]", line):
                break
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = re.match(r"^\s+- ([^\s#]+)", line)
            if m:
                items.append(m.group(1))
        return items

    def test_backup_exclude_and_hook_exclude_lists(self):
        """exclude is always applied; hookExclude only after a successful preHook."""
        block = self._backup_block()
        exclude = self._list_under(block, "exclude")
        hook_exclude = self._list_under(block, "hookExclude")
        self.assertEqual(
            exclude,
            ["keys", "tailscale", "tailscale-run", "data/backup/daily"],
            "unexpected x-app.backup.exclude: %r\n%s" % (exclude, block),
        )
        self.assertEqual(
            hook_exclude,
            ["usage.sqlite", "usage.sqlite-wal", "usage.sqlite-shm"],
            "unexpected x-app.backup.hookExclude: %r\n%s" % (hook_exclude, block),
        )
        combined = exclude + hook_exclude
        # The hook dump itself must stay in the archive (not in either list).
        self.assertNotIn("data/backup/usage.sqlite", combined)
        self.assertNotIn("backup/usage.sqlite", combined)
        self.assertNotIn("backup", combined)
        # data/backup/daily is the Engine-supported path (not backup/daily).
        self.assertNotIn("backup/daily", exclude)

    def test_check_compose_rejects_live_db_in_always_exclude(self):
        body = COMPOSE.read_text(encoding="utf-8")
        # Put the live db back under exclude (the pre-hookExclude shape).
        body = body.replace(
            """    exclude:
      - keys
      - tailscale
      - tailscale-run
      # Dated daily copies. #325 rejects globs, so these live under
      # data/backup/daily/ (write data/backup/daily, not backup/daily:
      # a slash path is instance-relative and is not auto-prefixed).
      # The hook dump data/backup/usage.sqlite is in neither list.
      - data/backup/daily
    hookExclude:
      - usage.sqlite
      - usage.sqlite-wal
      - usage.sqlite-shm
""",
            """    exclude:
      - keys
      - tailscale
      - tailscale-run
      - usage.sqlite
      - usage.sqlite-wal
      - usage.sqlite-shm
      - data/backup/daily
""",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            result = self._check(path)
            self.assertNotEqual(result.returncode, 0)
            combined = result.stderr + result.stdout
            self.assertIn("hookExclude", combined)
        finally:
            Path(path).unlink()

    def test_check_compose_rejects_unprefixed_daily_path(self):
        body = COMPOSE.read_text(encoding="utf-8").replace(
            "- data/backup/daily",
            "- backup/daily",
        )
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            result = self._check(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("data/backup/daily", result.stderr + result.stdout)
        finally:
            Path(path).unlink()

    def test_backup_declares_hook_method_and_collector_hooks(self):
        """idea#444 compose fields: method hook, fallback stop, hooks on collector."""
        block = self._backup_block()
        self.assertRegex(block, r"(?m)^    method:\s*hook\s*$", msg=block)
        self.assertRegex(block, r"(?m)^    hookTimeout:\s*300\s*$", msg=block)
        self.assertRegex(block, r"(?m)^    fallback:\s*stop\s*$", msg=block)
        self.assertRegex(block, r"(?m)^    preHook:", msg=block)
        self.assertRegex(block, r"(?m)^    postHook:", msg=block)
        self.assertIn("service: collector", block)
        self.assertIn("command: /app/scripts/backup-snapshot.sh", block)
        self.assertIn("command: /app/scripts/backup-cleanup.sh", block)
        pre = block.split("preHook:", 1)[1].split("postHook:", 1)[0]
        post = block.split("postHook:", 1)[1]
        self.assertIn("service: collector", pre)
        self.assertIn("/app/scripts/backup-snapshot.sh", pre)
        self.assertIn("service: collector", post)
        self.assertIn("/app/scripts/backup-cleanup.sh", post)
        self.assertTrue((REPO / "collector" / "scripts" / "backup-snapshot.sh").is_file())
        self.assertTrue((REPO / "collector" / "scripts" / "backup-cleanup.sh").is_file())
        # Scripts are on the ./collector bind (read-only at /app).
        compose = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("./collector:/app:ro", compose)

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
