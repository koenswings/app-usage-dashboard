"""idea#461: usage-dashboard 1.4 release compose.

Version labels and USAGE_DASHBOARD_VERSION are 1.4. The web digest pin is
kept from 1.3. The collector image is a baked python+packages pin; the
digest is unbuilt (64 zeros) until the arm64 image is built on a Pi.
Entrypoints and startup scripts must not install packages at runtime.
"""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "script" / "check-compose.mjs"
COMPOSE = REPO / "compose.yaml"
WEB_PIN = (
    "ghcr.io/koenswings/usage-dashboard-web:1.3"
    "@sha256:6ec777fb89b84cae93cc592b5cb96b9dea070c71cb25e892a8294af3f10f5dfc"
)
UNBUILT_COLLECTOR_DIGEST = "0" * 64
COLLECTOR_PIN = (
    "ghcr.io/koenswings/usage-dashboard-collector:1.4@sha256:" + UNBUILT_COLLECTOR_DIGEST
)
# Command-like package installs. Dockerfile RUN lines are not scanned.
RUNTIME_INSTALL_RE = re.compile(
    r"(?<![\w-])(apt-get|apt\s+install|apk\s+add|apk\s+install|"
    r"pip3?\s+install|npm\s+install|yum\s+install|dnf\s+install|"
    r"microdnf\s+install)\b"
)
STARTUP_GLOBS = (
    "collector/entrypoint.sh",
    "collector/sidecar-wrap.sh",
    "collector/scripts/*.sh",
    "web/entrypoint.sh",
)


def _strip_shell_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


class Release14Tests(unittest.TestCase):
    def _check(self, *args):
        return subprocess.run(
            ["node", str(CHECK), *args], capture_output=True, text=True, cwd=str(REPO)
        )

    def _text(self):
        return COMPOSE.read_text(encoding="utf-8")

    def test_release_check_passes_with_tag_1_4(self):
        r = self._check("--release", "--tag", "1.4", str(COMPOSE))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_release_check_refuses_tag_1_3(self):
        r = self._check("--release", "--tag", "1.3", str(COMPOSE))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("x-app.version '1.4' != tag '1.3'", r.stderr + r.stdout)

    def test_version_label_and_health_version_are_1_4(self):
        text = self._text()
        self.assertRegex(text, r'(?m)^  version: "1\.4"$')
        labels = re.findall(r'(?m)^      x-app-version: "([^"]+)"$', text)
        self.assertEqual(labels, ["1.4", "1.4", "1.4"])
        self.assertIn("- USAGE_DASHBOARD_VERSION=1.4\n", text)
        self.assertNotIn('x-app-version: "1.3"\n', text)
        self.assertNotIn('x-app-version: "1.2"', text)
        self.assertNotIn("USAGE_DASHBOARD_VERSION=1.3\n", text)

    def test_web_pin_is_kept_from_1_3(self):
        text = self._text()
        self.assertIn("    image: " + WEB_PIN + "\n", text)
        self.assertNotIn("usage-dashboard-web:1.4@", text)
        self.assertNotIn("DIGEST_PLACEHOLDER", text)

    def test_collector_pin_is_unbuilt_zero_digest(self):
        text = self._text()
        self.assertIn("    image: " + COLLECTOR_PIN + "\n", text)
        self.assertNotIn("image: python:3.12-slim-bookworm", text)
        # The 64-zero digest is the unbuilt marker; replace after the Pi build.
        self.assertIn(UNBUILT_COLLECTOR_DIGEST, text)

    def test_migration_note_is_1_3_to_1_4_no_data_migration(self):
        text = self._text()
        self.assertIn("1.3→1.4: no data migration.", text)
        self.assertIn("idea#461", text)
        self.assertIn("copied or recreated", text)
        self.assertIn("updateApp recreates the collector container", text)
        self.assertNotIn("1.2→1.3: no data migration.", text)

    def test_startup_scripts_do_not_install_packages(self):
        hits = []
        for pattern in STARTUP_GLOBS:
            for path in sorted(REPO.glob(pattern)):
                body = _strip_shell_comments(path.read_text(encoding="utf-8"))
                for i, line in enumerate(body.splitlines(), 1):
                    if RUNTIME_INSTALL_RE.search(line):
                        hits.append("%s:%s: %s" % (path.relative_to(REPO), i, line.strip()))
        self.assertEqual(hits, [], "runtime package installs in startup scripts:\n" + "\n".join(hits))


if __name__ == "__main__":
    unittest.main()
