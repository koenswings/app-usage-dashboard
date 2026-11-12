"""Regression: U-7 Set up uses only own copies with an ok day (idea#462, 1.2 acceptance).

Fixture: Pixel's idea03 fleet shape, copied verbatim from the 1.2 API
(tests/fixtures/accept-1.2-idea03). 1.2 judged the non-hooked
nextcloud-files-b-001 (no ok day) as an unknown copy, so setupStatus.nextcloud
came out complete:null with both items in missing AND unknown.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import thresholds as th
from src.aggregate import scorecard_from_weeks, setup_status_from_weeks
from src.thresholds import setup_status

FIX = Path(__file__).resolve().parent / "fixtures" / "accept-1.2-idea03"


def _instances(name):
    return json.loads((FIX / f"{name}.json").read_text())["instances"]


class PixelFleetShapeTests(unittest.TestCase):
    def setUp(self):
        self.nextcloud = _instances("nextcloud")
        self.kolibri = _instances("kolibri")
        self.kiwix = _instances("kiwix")
        self.served = json.loads((FIX / "school.json").read_text())["scorecard"]

    def test_fixture_is_pixels_shape(self):
        ids = {n["instance"]: n for n in self.nextcloud}
        self.assertEqual(len(ids), 5)
        b = ids["nextcloud-files-b-001"]
        self.assertIs(b["demo"], False)
        self.assertEqual(b["hookStatus"], "no-hook")
        self.assertIsNone(b["setup"])
        own = [n for n in self.nextcloud if n["setup"] is not None]
        self.assertEqual(sorted(n["instance"] for n in own), self.served["copies"]["nextcloud"])
        for n in own:
            self.assertEqual(n["setup"]["teacher"]["beyondSeed"], 0)
            self.assertEqual(n["setup"]["learner"]["beyondSeed"], 0)
        # 1.2 served the buggy verdict
        bad = self.served["setupStatus"]["nextcloud"]
        self.assertIsNone(bad["complete"])
        self.assertEqual(bad["unknown"], ["teacherBeyondSeed", "learnerBeyondSeed"])

    def test_nextcloud_part_is_false_with_both_missing_and_no_unknown(self):
        s = setup_status_from_weeks(self.kolibri, self.nextcloud, self.kiwix)
        self.assertEqual(
            s["nextcloud"],
            {
                "complete": False,
                "missing": ["teacherBeyondSeed", "learnerBeyondSeed"],
                "unknown": [],
                "passingInstanceIds": [],
            },
        )
        self.assertIs(s["complete"], False)

    def test_kolibri_part_unchanged_on_this_fleet(self):
        s = setup_status_from_weeks(self.kolibri, self.nextcloud, self.kiwix)
        self.assertEqual(s["kolibri"], self.served["setupStatus"]["kolibri"])

    def test_scorecard_end_to_end(self):
        card = scorecard_from_weeks(self.kolibri, self.nextcloud, self.kiwix, [], "2026-11-09")
        self.assertIs(card["setupStatus"]["complete"], False)
        self.assertEqual(card["setupStatus"]["nextcloud"]["unknown"], [])
        self.assertEqual(card["copies"]["nextcloud"], self.served["copies"]["nextcloud"])

    def test_order_of_copies_does_not_matter(self):
        s = setup_status_from_weeks(self.kolibri, list(reversed(self.nextcloud)), self.kiwix)
        self.assertIs(s["nextcloud"]["complete"], False)
        self.assertEqual(s["nextcloud"]["unknown"], [])

    def test_kolibri_same_flaw_fixed(self):
        """A non-hooked Kolibri copy with no ok day must not turn a decided part unknown."""
        stray = copy.deepcopy(self.kolibri[0])
        stray.update({"instance": "kolibri-files-b-001", "instanceId": "kolibri-files-b-001",
                      "hookStatus": "no-hook", "setup": None})
        s = setup_status_from_weeks(self.kolibri + [stray], self.nextcloud, self.kiwix)
        self.assertIs(s["kolibri"]["complete"], False)
        self.assertEqual(s["kolibri"]["missing"], ["coach", "class", "enrolledLearner"])
        self.assertEqual(s["kolibri"]["unknown"], [])

    def test_demo_copies_never_count(self):
        demo = copy.deepcopy([n for n in self.nextcloud if n["setup"] is not None][0])
        demo.update({"instance": "nextcloud-demo", "demo": True})
        demo["setup"]["teacher"]["beyondSeed"] = 3
        demo["setup"]["learner"]["beyondSeed"] = 3
        s = setup_status_from_weeks(self.kolibri, self.nextcloud + [demo], self.kiwix)
        self.assertIs(s["nextcloud"]["complete"], False)

    def test_only_unmeasured_own_copies_is_unknown_not_absent(self):
        only_b = [n for n in self.nextcloud if n["setup"] is None]
        s = setup_status_from_weeks(self.kolibri, only_b, self.kiwix)
        self.assertIsNone(s["nextcloud"]["complete"])
        self.assertEqual(s["nextcloud"]["missing"], [])
        self.assertEqual(s["nextcloud"]["unknown"], ["teacherBeyondSeed", "learnerBeyondSeed"])
        self.assertIs(s["complete"], False)  # Kolibri fails, so the whole verdict fails

    def test_no_own_nextcloud_at_all(self):
        s = setup_status_from_weeks(self.kolibri, [], self.kiwix)
        self.assertEqual(s["nextcloud"]["missing"], ["noOwnNextcloud"])


class MissingUnknownDisjointTests(unittest.TestCase):
    """An item is never in both missing and unknown, for any mix of copies."""

    def test_disjoint_over_two_copy_combinations(self):
        import itertools

        values = (1, 0, None)
        keys = [key for _, key in th.NEXTCLOUD_SETUP_CHECKS]
        names = [name for name, _ in th.NEXTCLOUD_SETUP_CHECKS]
        rows = [dict(zip(keys, v)) for v in itertools.product(values, repeat=2)] + [None]
        for a, b in itertools.product(rows, repeat=2):
            part = th.app_setup_status([("a", a), ("b", b)], th.NEXTCLOUD_SETUP_CHECKS, "noOwnNextcloud")
            msg = (a, b, part)
            self.assertFalse(set(part["missing"]) & set(part["unknown"]), msg)
            for name, key in th.NEXTCLOUD_SETUP_CHECKS:
                known = [r[key] for r in (a, b) if r is not None and r.get(key) is not None]
                if part["complete"] is True:
                    continue
                if known:
                    self.assertNotIn(name, part["unknown"], msg)
                if any(v == 0 for v in known):
                    self.assertIn(name, part["missing"], msg)

    def test_known_fail_on_one_copy_and_old_hook_copy(self):
        a = {"teacherBeyondSeed": 0, "learnerBeyondSeed": 0}
        old_hook = {"teacherBeyondSeed": None, "learnerBeyondSeed": None}
        s = setup_status([("k", {"coachesBeyondSeed": 1, "classes": 1, "learnersEnrolled": 1})],
                         [("a", a), ("o", old_hook)], True)
        self.assertEqual(s["nextcloud"]["missing"], ["teacherBeyondSeed", "learnerBeyondSeed"])
        self.assertEqual(s["nextcloud"]["unknown"], [])
        # Part verdict unchanged from 1.2: the measured old-hook copy might
        # still pass on its own, so the part stays null (grey), never true.
        self.assertIsNone(s["nextcloud"]["complete"])


if __name__ == "__main__":
    unittest.main()
