"""idea#443: usage-dashboard 1.1 release compose (hook backup + idea#446 verify lists)."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "script" / "check-compose.mjs"
COMPOSE = REPO / "compose.yaml"
WEB_PIN = (
    "ghcr.io/koenswings/usage-dashboard-web:1.0"
    "@sha256:9b5501f0690f02146217595f177496612d107aefd2bd56c181f84c7f1c678139"
)

VERIFY_BLOCK = """    verify:
      present:
        - .env
        - data/operators.json
        - collector/src/main.py
      absent:
        - keys
        - tailscale
        - tailscale-run
        - data/backup/daily
"""


def normalize(raw):
    """Same rule as agent-engine-dev src/utils/backupExclude.ts normalizeBackupExclude."""
    p = raw.strip()
    while p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    if "/" not in p and p != "data" and not p.startswith("."):
        p = "data/" + p
    return p


def covers(a, b):
    return a == b or b.startswith(a + "/")


class Release11Tests(unittest.TestCase):
    def _check(self, *args):
        return subprocess.run(
            ["node", str(CHECK), *args], capture_output=True, text=True, cwd=str(REPO)
        )

    def _check_body(self, body, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
            fh.write(body)
            path = fh.name
        try:
            return self._check(*args, path)
        finally:
            Path(path).unlink()

    def _text(self):
        return COMPOSE.read_text(encoding="utf-8")

    def _verify(self, key):
        block = self._text().split("    verify:\n", 1)[1]
        out, on = [], False
        for line in block.split("\n"):
            if re.match(r"^    \S", line) or re.match(r"^\S", line):
                break
            m = re.match(r"^      (\w+):\s*$", line)
            if m:
                on = m.group(1) == key
                continue
            m = re.match(r"^\s+- (\S+)", line)
            if on and m:
                out.append(m.group(1))
        return out

    def test_release_check_passes_with_tag_1_1(self):
        r = self._check("--release", "--tag", "1.1", str(COMPOSE))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_version_label_and_health_version_are_1_1(self):
        text = self._text()
        self.assertRegex(text, r'(?m)^  version: "1\.1"$')
        labels = re.findall(r'(?m)^      x-app-version: "([^"]+)"$', text)
        self.assertEqual(labels, ["1.1", "1.1", "1.1"])
        self.assertIn("- USAGE_DASHBOARD_VERSION=1.1\n", text)
        self.assertNotIn('x-app-version: "1.0"', text)

    def test_web_pin_is_9b5501f0(self):
        self.assertIn("    image: " + WEB_PIN + "\n", self._text())

    def test_backup_method_hook_present(self):
        text = self._text()
        self.assertRegex(text, r"(?m)^    method: hook$")
        self.assertRegex(text, r"(?m)^    fallback: stop$")

    def test_verify_lists_hold_for_hook_and_fallback_archives(self):
        present = [normalize(p) for p in self._verify("present")]
        absent = [normalize(a) for a in self._verify("absent")]
        self.assertEqual(present, [".env", "data/operators.json", "collector/src/main.py"])
        self.assertEqual(
            absent, ["data/keys", "data/tailscale", "data/tailscale-run", "data/backup/daily"]
        )
        # A fallback-stop archive drops hookExclude: live db packed, no dump.
        # A hook archive: dump packed, live db excluded. Neither may be listed.
        for p in present:
            for path in ("data/usage.sqlite", "data/backup/usage.sqlite"):
                self.assertFalse(covers(p, path) or covers(path, p), p)
        for a in absent:
            for path in ("data/usage.sqlite", "data/backup/usage.sqlite") + tuple(present):
                self.assertFalse(covers(a, path), (a, path))

    def test_release_requires_verify_block_for_hook(self):
        body = self._text().replace(VERIFY_BLOCK, "")
        self.assertNotEqual(body, self._text())
        r = self._check_body(body, "--release", "--tag", "1.1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("x-app.backup.verify", r.stderr)
        # Without --release the block stays optional.
        self.assertEqual(self._check_body(body).returncode, 0)

    def _with_present(self, item):
        return self._text().replace("        - .env\n", "        - .env\n        - %s\n" % item, 1)

    def _with_absent(self, item):
        return self._text().replace(
            "        - data/backup/daily\n", "        - data/backup/daily\n        - %s\n" % item, 1
        )

    def test_rejects_hook_dump_in_present(self):
        r = self._check_body(self._with_present("data/backup/usage.sqlite"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("HOOK_FALLBACK", r.stderr)

    def test_rejects_live_db_in_present(self):
        for item in ("data/usage.sqlite", "usage.sqlite"):
            r = self._check_body(self._with_present(item))
            self.assertNotEqual(r.returncode, 0, item)
            self.assertIn("live db", r.stderr)

    def test_rejects_live_db_in_absent(self):
        for item in ("usage.sqlite", "data/usage.sqlite-wal", "data"):
            r = self._check_body(self._with_absent(item))
            self.assertNotEqual(r.returncode, 0, item)
            self.assertIn("HOOK_FALLBACK", r.stderr)

    def test_rejects_hook_dump_in_absent(self):
        for item in ("data/backup/usage.sqlite", "data/backup"):
            r = self._check_body(self._with_absent(item))
            self.assertNotEqual(r.returncode, 0, item)
            self.assertIn("hook dump", r.stderr)

    def test_rejects_excluded_path_in_present(self):
        r = self._check_body(self._with_present("data/keys/pull_key"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("under exclude", r.stderr)

    def test_rejects_bare_name_in_present(self):
        # compose.yaml would normalise to data/compose.yaml.
        r = self._check_body(self._with_present("compose.yaml"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("data/compose.yaml", r.stderr)

    def test_rejects_absent_covering_present(self):
        r = self._check_body(self._with_absent("collector/src"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("covers present", r.stderr)

    def test_rejects_unsafe_paths(self):
        for item in ("../etc", "/etc/passwd", "data/*.sqlite"):
            r = self._check_body(self._with_absent(item))
            self.assertNotEqual(r.returncode, 0, item)
            self.assertIn("not an allowed path", r.stderr)


if __name__ == "__main__":
    unittest.main()
