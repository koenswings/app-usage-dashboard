import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src.presence import cover_week, derive_segments, overlay_collector_gaps, parse_ts, rollup_day, week_bounds


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

    def test_cover_week_fills_holes_and_sums_to_five_days(self):
        segs = derive_segments([
            sample("2026-11-09T08:00:00+02:00", "b1", 100),
            sample("2026-11-09T12:00:00+02:00", "b1", 14500),
        ])
        start, end = week_bounds("2026-11-09", "+02:00")
        self.assertEqual(start, parse_ts("2026-11-09T00:00:00+02:00"))
        self.assertEqual(end, parse_ts("2026-11-14T00:00:00+02:00"))
        covered = cover_week(segs, start, end)
        self.assertEqual(parse_ts(covered[0]["start"]), start)
        self.assertEqual(parse_ts(covered[-1]["end"]), end)
        total = sum((parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds() for s in covered)
        self.assertEqual(total, (end - start).total_seconds())
        self.assertEqual(total, 5 * 86400)
        for prev, nxt in zip(covered, covered[1:]):
            self.assertEqual(parse_ts(prev["end"]), parse_ts(nxt["start"]))
        states = [s["state"] for s in covered]
        self.assertIn("on", states)
        self.assertIn("gapUnknown", states)
        self.assertEqual(covered[0]["state"], "gapUnknown")
        self.assertFalse(covered[0]["lengthKnown"])
        on = [s for s in covered if s["state"] == "on"][0]
        self.assertEqual(on["start"], "2026-11-09T08:00:00+02:00")
        self.assertEqual(on["end"], "2026-11-09T12:00:00+02:00")
        self.assertTrue(on["lengthKnown"])

    def test_cover_week_uses_collector_gap_not_on(self):
        segs = derive_segments([
            sample("2026-11-09T08:00:00+02:00", "b1", 100),
            sample("2026-11-09T12:00:00+02:00", "b1", 14500),
        ])
        start, end = week_bounds("2026-11-09", "+02:00")
        covered = cover_week(segs, start, end, [{
            "start": "2026-11-09T13:00:00+02:00",
            "end": "2026-11-09T15:00:00+02:00",
        }])
        by_state = {}
        for seg in covered:
            by_state.setdefault(seg["state"], []).append(seg)
        self.assertEqual(len(by_state["on"]), 1)
        self.assertEqual(by_state["on"][0]["start"], "2026-11-09T08:00:00+02:00")
        gaps = by_state["collectorGap"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["start"], "2026-11-09T13:00:00+02:00")
        self.assertEqual(gaps[0]["end"], "2026-11-09T15:00:00+02:00")
        self.assertTrue(gaps[0]["lengthKnown"])
        # A collector gap that overlaps measured on must not punch through.
        covered2 = cover_week(segs, start, end, [{
            "start": "2026-11-09T09:00:00+02:00",
            "end": "2026-11-09T10:00:00+02:00",
        }])
        self.assertFalse(any(s["state"] == "collectorGap" for s in covered2))
        on = [s for s in covered2 if s["state"] == "on"][0]
        self.assertEqual(on["start"], "2026-11-09T08:00:00+02:00")
        self.assertEqual(on["end"], "2026-11-09T12:00:00+02:00")

    def test_cover_week_empty_is_all_gap_unknown(self):
        start, end = week_bounds("2026-11-09", "+02:00")
        covered = cover_week([], start, end)
        self.assertEqual(len(covered), 1)
        self.assertEqual(covered[0]["state"], "gapUnknown")
        self.assertFalse(covered[0]["lengthKnown"])
        self.assertEqual(covered[0]["start"], "2026-11-09T00:00:00+02:00")
        self.assertEqual(covered[0]["end"], "2026-11-14T00:00:00+02:00")

    def test_cover_week_open_collector_gap_not_known(self):
        start, end = week_bounds("2026-11-09", "+02:00")
        now = parse_ts("2026-11-11T10:00:00+02:00")
        covered = cover_week([], start, end, [{
            "start": "2026-11-10T00:00:00+02:00",
            "end": None,
        }], now=now)
        states = [(s["state"], s["start"], s["end"], s["lengthKnown"]) for s in covered]
        gap = [s for s in covered if s["state"] == "collectorGap"]
        self.assertEqual(len(gap), 1)
        self.assertEqual(gap[0]["start"], "2026-11-10T00:00:00+02:00")
        self.assertEqual(gap[0]["end"], "2026-11-11T10:00:00+02:00")
        self.assertFalse(gap[0]["lengthKnown"])
        self.assertEqual(parse_ts(covered[-1]["end"]), end)
        total = sum((parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds() for s in covered)
        self.assertEqual(total, 5 * 86400)
        _ = states

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
