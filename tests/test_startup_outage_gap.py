"""Startup collector-offline gap for whole-hub outages (idea#414 / idea#445)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import db
from src import main as mainmod
from src import presence as presence_mod


THRESHOLD = 600
NOW = datetime(2026, 11, 11, 21, 59, tzinfo=timezone.utc)


def _conn(tmp: str):
    return db.connect(os.path.join(tmp, "usage.sqlite"))


def _insert_uplink(conn, ts: datetime, engine: str = "idea03") -> None:
    conn.execute(
        """INSERT INTO uplink_samples(engine, timestamp, online, last_seen, via, latency_ms)
           VALUES (?, ?, 1, ?, NULL, NULL)""",
        (engine, presence_mod.rfc3339(ts), presence_mod.rfc3339(ts)),
    )
    conn.commit()


def _insert_presence(conn, ts: datetime, engine: str = "idea03") -> None:
    day = ts.astimezone(timezone.utc).date().isoformat()
    conn.execute(
        """INSERT INTO presence_samples(engine, day, ts, payload, boot_id, uptime_s, ntp_synced)
           VALUES (?, ?, ?, '{}', NULL, NULL, 1)""",
        (engine, day, presence_mod.rfc3339(ts)),
    )
    conn.commit()


def _gaps(conn):
    return list(conn.execute("SELECT start, end, reason FROM collector_gaps ORDER BY id"))


class StartupOutageGapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = _conn(self.tmp)

    def tearDown(self):
        self.conn.close()

    def test_last_sample_10_min_ago_creates_a_closed_gap(self):
        last = NOW - timedelta(seconds=THRESHOLD)
        _insert_uplink(self.conn, last)
        reason = mainmod.record_startup_outage_gap(
            self.conn, now=NOW, threshold_s=THRESHOLD,
        )
        self.assertEqual(reason, mainmod.GAP_COLLECTOR_OFFLINE)
        rows = _gaps(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "collector-offline")
        self.assertEqual(presence_mod.parse_ts(rows[0]["start"]), last)
        self.assertEqual(presence_mod.parse_ts(rows[0]["end"]), NOW)

    def test_latest_sample_is_max_across_presence_and_uplink(self):
        older = NOW - timedelta(minutes=30)
        newer = NOW - timedelta(minutes=20)
        _insert_uplink(self.conn, older)
        _insert_presence(self.conn, newer)
        self.assertEqual(mainmod.latest_sample_time(self.conn), newer)
        reason = mainmod.record_startup_outage_gap(
            self.conn, now=NOW, threshold_s=THRESHOLD,
        )
        self.assertEqual(reason, mainmod.GAP_COLLECTOR_OFFLINE)
        start = presence_mod.parse_ts(_gaps(self.conn)[0]["start"])
        self.assertEqual(start, newer)

    def test_recent_sample_creates_none(self):
        _insert_uplink(self.conn, NOW - timedelta(minutes=5))
        self.assertIsNone(
            mainmod.record_startup_outage_gap(self.conn, now=NOW, threshold_s=THRESHOLD)
        )
        self.assertEqual(_gaps(self.conn), [])

    def test_empty_db_creates_none(self):
        self.assertIsNone(mainmod.latest_sample_time(self.conn))
        self.assertIsNone(
            mainmod.record_startup_outage_gap(self.conn, now=NOW, threshold_s=THRESHOLD)
        )
        self.assertEqual(_gaps(self.conn), [])

    def test_restart_twice_creates_no_duplicate(self):
        last = NOW - timedelta(minutes=15)
        _insert_presence(self.conn, last)
        first = mainmod.record_startup_outage_gap(
            self.conn, now=NOW, threshold_s=THRESHOLD,
        )
        self.assertEqual(first, mainmod.GAP_COLLECTOR_OFFLINE)
        later = NOW + timedelta(seconds=8)
        second = mainmod.record_startup_outage_gap(
            self.conn, now=later, threshold_s=THRESHOLD,
        )
        self.assertIsNone(second)
        self.assertEqual(len(_gaps(self.conn)), 1)

    def test_already_open_gap_is_not_duplicated(self):
        last = NOW - timedelta(minutes=15)
        _insert_uplink(self.conn, last)
        # A leftover open gap that started after the last sample (watchdog
        # opened it mid-outage before the process died).
        mid = last + timedelta(minutes=5)
        self.conn.execute(
            "INSERT INTO collector_gaps(start, end, reason) VALUES (?, NULL, ?)",
            (presence_mod.rfc3339(mid), "sidecar-offline"),
        )
        self.conn.commit()
        self.assertIsNone(
            mainmod.record_startup_outage_gap(self.conn, now=NOW, threshold_s=THRESHOLD)
        )
        rows = _gaps(self.conn)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["end"])
        self.assertEqual(rows[0]["reason"], "sidecar-offline")
        # Start is backdated so the strip covers the whole outage.
        self.assertEqual(presence_mod.parse_ts(rows[0]["start"]), last)

    def test_cover_week_shows_the_gap_like_other_collector_gaps(self):
        last = NOW - timedelta(minutes=10)
        _insert_uplink(self.conn, last)
        mainmod.record_startup_outage_gap(self.conn, now=NOW, threshold_s=THRESHOLD)
        gap_list = [
            {"start": row["start"], "end": row["end"]}
            for row in self.conn.execute("SELECT start, end FROM collector_gaps")
        ]
        week_start = datetime(2026, 11, 9, tzinfo=timezone.utc)  # Monday
        week_end = datetime(2026, 11, 14, tzinfo=timezone.utc)  # Saturday
        covered = presence_mod.cover_week([], week_start, week_end, gap_list, now=NOW)
        gaps = [s for s in covered if s["state"] == "collectorGap"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(presence_mod.parse_ts(gaps[0]["start"]), last)
        self.assertEqual(presence_mod.parse_ts(gaps[0]["end"]), NOW)
        self.assertTrue(gaps[0]["lengthKnown"])

    def test_main_records_the_gap_before_serving(self):
        last = NOW - timedelta(minutes=12)
        _insert_uplink(self.conn, last)
        self.conn.close()
        env = {
            "DATA_DIR": self.tmp,
            "COLLECTOR_BIND": "127.0.0.1:0",
            "IDEA_USAGE_KOEN_PASSWORD": "koen911!",
            "IDEA_USAGE_MARCO_PASSWORD": "marco911!",
            "IDEA_USAGE_ONCE": "1",
            "COLLECTOR_OFFLINE_AFTER_S": "600",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        served = {}

        def fake_serve(conn, bind):
            served["gaps"] = [
                (row["start"], row["end"], row["reason"])
                for row in conn.execute("SELECT start, end, reason FROM collector_gaps")
            ]
            served["conn"] = conn

            class _Srv:
                def serve_forever(self):
                    return None

            return _Srv()

        orig_serve = mainmod.serve
        orig_now = mainmod.db.now_rfc3339
        mainmod.serve = fake_serve
        mainmod.db.now_rfc3339 = lambda: presence_mod.rfc3339(NOW)
        try:
            self.assertEqual(mainmod.main(), 0)
            self.assertEqual(len(served["gaps"]), 1)
            self.assertEqual(served["gaps"][0][2], "collector-offline")
            self.assertEqual(presence_mod.parse_ts(served["gaps"][0][0]), last)
            self.assertEqual(presence_mod.parse_ts(served["gaps"][0][1]), NOW)
        finally:
            mainmod.serve = orig_serve
            mainmod.db.now_rfc3339 = orig_now
            conn = served.get("conn")
            if conn is not None:
                conn.close()
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
