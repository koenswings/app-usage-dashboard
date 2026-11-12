"""idea#462: usage-dashboard 1.2 release compose (superseded by 1.3).

The 1.2 version labels, release check and migration note moved to
tests/test_release_1_3.py. Only the 1.2 web pin stays here, as the
placeholder until the 1.3 web digest is pinned.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "compose.yaml"
WEB_PIN = (
    "ghcr.io/koenswings/usage-dashboard-web:1.2"
    "@sha256:706fdd6833d5131cffe80e2410ace37899b8942fa8b0cb5d3e8088a103edde45"
)


class Release12Tests(unittest.TestCase):
    def test_web_pin_is_still_706fdd68_until_1_3_image_lands(self):
        # 1.3 keeps this pin as a placeholder until the new web digest is pinned.
        self.assertIn("    image: " + WEB_PIN + "\n", COMPOSE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
