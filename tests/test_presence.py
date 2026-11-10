import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src.presence import derive_segments, overlay_collector_gaps, rollup_day


def sample(ts, boot, uptime, synced=True):
    return {"ts": ts, "bootId": boot, "uptimeS": uptime, "ntpSynced": synced}


class PresenceTests(unittest.TestCase):
    def test_same_boot_is_on(self):
        segs = derive_segments([
            sample("2026-11-09T08:00:00+02:00", "b1", 100),
            sample("2026-11-09T08:05:00+02:00", "b1", 400),
            sample("2026-11-09T08:10:00+02:00", "b1", 700),
        ])
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0]["state"], "on")
        self.assertTrue(segs[0]["lengthKnown"])
        self.assertEqual(segs[0]["start"], "2026-11-09T08:00:00+02:00")
        self.assertEqual(segs[0]["end"], "2026-11-09T08:10:00+02:00")

    def test_reboot_synced_is_off(self):
        segs = derive_segments([
            sample("2026-11-09T16:00:00+02:00", "b1", 8000),
            sample("2026-11-10T07:10:00+02:00", "b2", 600, synced=True),
        ])
        states = [s["state"] for s in segs]
        self.assertIn("on", states)
        self.assertIn("off", states)
        off = [s for s in segs if s["state"] == "off"][0]
        self.assertTrue(off["lengthKnown"])

    def test_unsynced_next_is_gap_unknown(self):
        segs = derive_segments([
            sample("2026-11-09T16:00:00+02:00", "b1", 8000, synced=True),
            sample("2026-11-10T07:10:00+02:00", "b2", 600, synced=False),
        ])
        states = [s["state"] for s in segs]
        self.assertIn("gapUnknown", states)
        gap = [s for s in segs if s["state"] == "gapUnknown"][0]
        self.assertFalse(gap["lengthKnown"])

    def test_collector_gap_overlays_unknown_not_on(self):
        segs = derive_segments([
            sample("2026-11-09T08:00:00+02:00", "b1", 100),
            sample("2026-11-09T10:00:00+02:00", "b1", 7300),
        ])
        out = overlay_collector_gaps(segs, [{
            "start": "2026-11-09T08:30:00+02:00",
            "end": "2026-11-09T09:00:00+02:00",
        }])
        # Observed on remains; a hole-only collectorGap is added when not covered.
        states = {s["state"] for s in out}
        self.assertIn("on", states)

    def test_collector_gap_on_empty_history(self):
        out = overlay_collector_gaps([], [{
            "start": "2026-11-09T10:00:00+02:00",
            "end": "2026-11-09T12:00:00+02:00",
        }])
        self.assertEqual(out[0]["state"], "collectorGap")
        self.assertFalse(out[0]["lengthKnown"])

    def test_rollup_school_hours(self):
        segs = [{
            "state": "on",
            "start": "2026-11-09T06:00:00+02:00",
            "end": "2026-11-09T16:00:00+02:00",
            "lengthKnown": True,
        }]
        tz = datetime.fromisoformat("2026-11-09T00:00:00+02:00").tzinfo
        roll = rollup_day(segs, "2026-11-09", tz)
        self.assertEqual(roll["onMinutes"], 600)
        self.assertEqual(roll["schoolHoursOnMinutes"], 540)  # 07:00-16:00


if __name__ == "__main__":
    unittest.main()
