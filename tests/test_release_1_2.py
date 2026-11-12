"""idea#462: usage-dashboard 1.2 release compose.

Version labels and USAGE_DASHBOARD_VERSION are 1.2. The web digest pin is
the idea03 buildx linux/arm64 image (single-platform manifest).
"""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "script" / "check-compose.mjs"
COMPOSE = REPO / "compose.yaml"
WEB_PIN = (
    "ghcr.io/koenswings/usage-dashboard-web:1.2"
    "@sha256:706fdd6833d5131cffe80e2410ace37899b8942fa8b0cb5d3e8088a103edde45"
)


class Release12Tests(unittest.TestCase):
    def _check(self, *args):
        return subprocess.run(
            ["node", str(CHECK), *args], capture_output=True, text=True, cwd=str(REPO)
        )

    def _text(self):
        return COMPOSE.read_text(encoding="utf-8")

    def test_release_check_passes_with_tag_1_2(self):
        r = self._check("--release", "--tag", "1.2", str(COMPOSE))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_version_label_and_health_version_are_1_2(self):
        text = self._text()
        self.assertRegex(text, r'(?m)^  version: "1\.2"$')
        labels = re.findall(r'(?m)^      x-app-version: "([^"]+)"$', text)
        self.assertEqual(labels, ["1.2", "1.2", "1.2"])
        self.assertIn("- USAGE_DASHBOARD_VERSION=1.2\n", text)
        self.assertNotIn('x-app-version: "1.1"', text)
        self.assertNotIn('x-app-version: "1.0"', text)
        self.assertNotIn("USAGE_DASHBOARD_VERSION=1.1", text)

    def test_web_pin_is_706fdd68(self):
        text = self._text()
        self.assertIn("    image: " + WEB_PIN + "\n", text)
        self.assertNotIn("PLACEHOLDER", text)
        self.assertNotIn("usage-dashboard-web:1.0@", text)

    def test_migration_note_is_1_1_to_1_2_no_data_migration(self):
        text = self._text()
        self.assertIn("1.1→1.2: no data migration.", text)
        self.assertIn("real hook names", text)
        self.assertIn("idea#462", text)
        self.assertIn("new UI", text)
        self.assertIn("never copied or recreated", text)
        self.assertNotIn("1.1 adds the online backup hook", text)


if __name__ == "__main__":
    unittest.main()
