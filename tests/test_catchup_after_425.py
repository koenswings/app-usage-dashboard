"""Collector fixture for Axle's idea#425 fix (agent-engine-dev#312).

After the Engine catch-up change, an idea03-like export no longer stamps
currently installed apps onto days before they existed. This fixture is the
inventory `idea-usage-export` would produce after that fix:

- `since 2026-10-28`: nextcloud-files-b-001 has day records for 10-28 to
  11-10, there is no usage-dashboard-* on any past day, and all presence
  samples are on 11-11.
- `since 2026-11-11`: 0 day records, and presence is the 11-11 lines.
- `since 2026-11-12`: nothing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import db
from src.api import serve
from src.parse import interpret_export, parse_since_stream
from src.presence import parse_ts
from src.pull import store_export


ENGINE = "idea03"
DEP = "dep-idea03-425"
SCHOOL = "Pool Pi 3"
TZ = "Europe/Brussels"
COLLECTED_AT = "2026-11-11T00:51:34+01:00"
PULLED_AT = "2026-11-11T02:30:00+01:00"
DASHBOARD = "usage-dashboard-m7mhutyviv1z5xgryc4"
NEXTCLOUD = "nextcloud-files-b-001"

DAY_START = date(2026, 10, 28)
DAY_END = date(2026, 11, 10)  # inclusive; no 11-11 day file yet
PRESENCE_TS = (
    "2026-11-11T00:51:34+01:00",
    "2026-11-11T08:00:00+01:00",
    "2026-11-11T12:00:00+01:00",
    "2026-11-11T16:30:00+01:00",
)


def _days(start: date, end: date) -> list[str]:
    out = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


NEXTCLOUD_DAYS = _days(DAY_START, DAY_END)


def nextcloud_day(day: str) -> dict:
    return {
        "schema": "idea-usage-day/1",
        "engine": ENGINE,
        "day": day,
        "app": "nextcloud",
        "instance": NEXTCLOUD,
        "name": "Nextcloud Files B",
        "demo": False,
        "listed": True,
        "clock": {"synced": True, "correctedBoots": 0},
        "collectedAt": COLLECTED_AT,
        "hookStatus": "no-hook",
    }


def dashboard_day(day: str = "2026-11-11") -> dict:
    return {
        "schema": "idea-usage-day/1",
        "engine": ENGINE,
        "day": day,
        "app": "other",
        "instance": DASHBOARD,
        "name": "Usage Dashboard",
        "demo": False,
        "listed": True,
        "clock": {"synced": True, "correctedBoots": 0},
        "collectedAt": "2026-11-11T02:22:00+01:00",
        "hookStatus": "no-hook",
    }


def presence_payload(ts: str, uptime: int) -> dict:
    return {
        "schema": "idea-usage-presence/1",
        "engine": ENGINE,
        "ts": ts,
        "day": ts[:10],
        "bootId": "boot-2026-11-11",
        "uptimeS": uptime,
        "ntpSynced": True,
        "engineUp": True,
        "instancesUp": [NEXTCLOUD],
        "tempC": 48.0,
        "throttled": "0x0",
    }


def presence_records_11_11() -> list[dict]:
    # Same boot, later samples have larger uptimes so derive_segments can
    # paint an on stretch on 11-11 only.
    uptimes = (60, 60 + 7 * 3600 + 8 * 60 + 26, 60 + 11 * 3600 + 8 * 60 + 26, 60 + 15 * 3600 + 38 * 60 + 26)
    recs = []
    for ts, uptime in zip(PRESENCE_TS, uptimes):
        payload = presence_payload(ts, uptime)
        recs.append({"type": "presence", "schema": "idea-usage-presence/1", "day": "2026-11-11", "payload": payload})
    return recs


def day_record(payload: dict) -> dict:
    return {
        "type": "day",
        "schema": "idea-usage-day/1",
        "day": payload["day"],
        "instance": payload["instance"],
        "payload": payload,
    }


def end_record(since: str, day_count: int, presence_count: int) -> dict:
    return {
        "type": "end",
        "schema": "idea-usage-export/1",
        "since": since,
        "engine": ENGINE,
        "usageMonitoring": "on",
        "counts": {"day": day_count, "sample": 0, "presence": presence_count},
        "errors": 0,
    }


def to_ndjson(records: list[dict]) -> str:
    return "".join(json.dumps(rec) + "\n" for rec in records)


def export_since_2026_10_28() -> str:
    recs = [day_record(nextcloud_day(day)) for day in NEXTCLOUD_DAYS]
    recs.extend(presence_records_11_11())
    recs.append(end_record("2026-10-28", len(NEXTCLOUD_DAYS), len(PRESENCE_TS)))
    return to_ndjson(recs)


def export_since_2026_11_11() -> str:
    recs = list(presence_records_11_11())
    recs.append(end_record("2026-11-11", 0, len(PRESENCE_TS)))
    return to_ndjson(recs)


def export_since_2026_11_12() -> str:
    return to_ndjson([end_record("2026-11-12", 0, 0)])


def dashboard_day_stream() -> str:
    recs = [day_record(dashboard_day()), end_record("2026-11-11", 1, 0)]
    return to_ndjson(recs)


def instance_ids(payload: dict) -> list[str]:
    return [item["instance"] for item in payload.get("instances") or []]


def dashboard_ids(payload: dict) -> list[str]:
    return [i for i in instance_ids(payload) if i.startswith("usage-dashboard")]


def covers_day(segments: list[dict], day: str) -> list[str]:
    """States that overlap [day 00:00, next day 00:00) in Europe/Brussels."""
    start = parse_ts("%sT00:00:00+01:00" % day)
    end = start + timedelta(days=1)
    states = []
    for seg in segments:
        a, b = parse_ts(seg["start"]), parse_ts(seg["end"])
        if b > start and a < end:
            states.append(seg["state"])
    return states


class CatchupAfter425StreamTests(unittest.TestCase):
    """The three since-windows match the post-fix idea03 inventory."""

    def test_since_2026_10_28_has_nextcloud_only_and_presence_on_11_11(self):
        parsed = parse_since_stream(export_since_2026_10_28())
        days = [rec["payload"]["day"] for rec in parsed["days"]]
        instances = {rec["payload"]["instance"] for rec in parsed["days"]}
        self.assertEqual(days, NEXTCLOUD_DAYS)
        self.assertEqual(len(days), 14)
        self.assertEqual(instances, {NEXTCLOUD})
        self.assertFalse(any(i.startswith("usage-dashboard") for i in instances))
        self.assertTrue(all(rec["day"] == "2026-11-11" for rec in parsed["presence"]))
        self.assertEqual(len(parsed["presence"]), 4)
        self.assertEqual(parsed["end"]["counts"]["day"], 14)
        self.assertEqual(parsed["end"]["counts"]["presence"], 4)

    def test_since_2026_11_11_has_no_day_records(self):
        parsed = parse_since_stream(export_since_2026_11_11())
        self.assertEqual(parsed["days"], [])
        self.assertEqual(parsed["end"]["counts"]["day"], 0)
        self.assertTrue(all(rec["day"] == "2026-11-11" for rec in parsed["presence"]))
        self.assertEqual(len(parsed["presence"]), 4)

    def test_since_2026_11_12_is_empty(self):
        parsed = parse_since_stream(export_since_2026_11_12())
        self.assertEqual(parsed["days"], [])
        self.assertEqual(parsed["presence"], [])
        self.assertEqual(parsed["samples"], [])
        self.assertEqual(parsed["end"]["counts"], {"day": 0, "sample": 0, "presence": 0})


class CatchupAfter425ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "usage.sqlite")
        self.conn = db.connect(self.db_path)
        registry = os.path.join(self.tmp, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump({"kits": [{
                "engine": ENGINE,
                "tailscaleName": ENGINE,
                "school": SCHOOL,
                "deploymentId": DEP,
                "timezone": TZ,
                "note": "idea#425 post-fix inventory",
            }]}, fh)
        db.load_registry(self.conn, registry)
        os.environ["IDEA_USAGE_ADMIN_PASSWORD"] = "admin911!"
        os.environ["IDEA_USAGE_SESSION_SECRET"] = "test-secret"
        self.server = serve(self.conn, "127.0.0.1:0")
        host, port = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://%s:%s" % (host, port)
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.conn.close()

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = Request(self.base + path, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def login(self):
        status, payload = self.call("POST", "/api/v1/session", {"username": "admin", "password": "admin911!"})
        self.assertEqual(status, 200, payload)
        self.assertTrue(payload["authenticated"])

    def ingest(self, stream: str, pulled_at: str = PULLED_AT):
        parsed = interpret_export(0, stream, "")
        store_export(self.conn, ENGINE, parsed, pulled_at, DEP)
        self.conn.commit()
        return parsed

    def instances(self, week: str):
        status, payload = self.call("GET", "/api/v1/weeks/%s/schools/%s/instances" % (week, DEP))
        self.assertEqual(status, 200, payload)
        return payload

    def presence(self, week: str):
        status, payload = self.call("GET", "/api/v1/weeks/%s/schools/%s/presence" % (week, DEP))
        self.assertEqual(status, 200, payload)
        return payload

    def test_older_weeks_have_no_dashboard_gap_unknown_and_oct_26_27_are_a_gap(self):
        self.ingest(export_since_2026_10_28())
        # A later pull of the same day (since 11-11 / 11-12) must not invent
        # historical dashboard day files.
        self.ingest(export_since_2026_11_11())
        self.ingest(export_since_2026_11_12())
        self.login()

        for week in ("2026-10-26", "2026-11-02"):
            payload = self.instances(week)
            self.assertIn(NEXTCLOUD, instance_ids(payload), week)
            self.assertEqual(dashboard_ids(payload), [], week)

        for week in ("2026-10-26", "2026-11-02"):
            pres = self.presence(week)
            states = {seg["state"] for seg in pres["segments"]}
            self.assertEqual(states, {"gapUnknown"}, week)
            on_days = [d for d in pres.get("days") or [] if d.get("onMinutes") or d.get("schoolHoursOnMinutes")]
            self.assertEqual(on_days, [], week)

        # 10-26 and 10-27 are a gap: no day files (export starts 10-28) and
        # the presence cover for those dates is gapUnknown.
        rows = self.conn.execute(
            "SELECT DISTINCT day FROM daily_summaries WHERE day IN ('2026-10-26', '2026-10-27') ORDER BY day"
        ).fetchall()
        self.assertEqual([r["day"] for r in rows], [])
        week_pres = self.presence("2026-10-26")
        for day in ("2026-10-26", "2026-10-27"):
            self.assertEqual(set(covers_day(week_pres["segments"], day)), {"gapUnknown"}, day)

        # Week of 11-09 still has nextcloud (11-09 and 11-10) but no dashboard
        # until an 11-11 day file exists.
        week_now = self.instances("2026-11-09")
        self.assertIn(NEXTCLOUD, instance_ids(week_now))
        self.assertEqual(dashboard_ids(week_now), [])

    def test_dashboard_appears_in_week_11_09_only_after_11_11_day_file(self):
        self.ingest(export_since_2026_10_28())
        self.login()
        before = self.instances("2026-11-09")
        self.assertIn(NEXTCLOUD, instance_ids(before))
        self.assertEqual(dashboard_ids(before), [])

        self.ingest(dashboard_day_stream(), pulled_at="2026-11-11T18:00:00+01:00")
        after = self.instances("2026-11-09")
        self.assertIn(NEXTCLOUD, instance_ids(after))
        self.assertEqual(dashboard_ids(after), [DASHBOARD])

        # The new day file must not backfill earlier weeks.
        for week in ("2026-10-26", "2026-11-02"):
            payload = self.instances(week)
            self.assertEqual(dashboard_ids(payload), [], week)
            self.assertIn(NEXTCLOUD, instance_ids(payload), week)


if __name__ == "__main__":
    unittest.main()
