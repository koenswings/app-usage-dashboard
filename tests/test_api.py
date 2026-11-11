import json
import os
import sys
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import db
from src.api import serve
from src.pull import store_export


WEEK = "2026-11-09"  # Monday (original fixture week)
FOUR_STATE_WEEK = "2026-11-02"  # Monday — on, off, collectorGap, gapUnknown
COLLECTOR_GAP = {
    "start": "2026-11-05T10:00:00+02:00",
    "end": "2026-11-05T16:00:00+02:00",
    "reason": "sidecar-offline",
}


def presence_payload(engine, ts, boot, uptime, synced=True):
    return {
        "schema": "idea-usage-presence/1",
        "engine": engine,
        "ts": ts,
        "bootId": boot,
        "uptimeS": uptime,
        "ntpSynced": synced,
        "engineUp": True,
        "instancesUp": ["kolibri-a"],
        "tempC": 50.0,
        "throttled": "0x0",
    }


def export_for(engine="happy-zebra"):
    day_ok = {
        "schema": "idea-usage-day/1",
        "engine": engine,
        "day": "2026-11-09",
        "app": "kolibri",
        "instance": "kolibri-a",
        "name": "Kolibri",
        "demo": False,
        "listed": True,
        "clock": {"synced": True, "correctedBoots": 0},
        "collectedAt": "2026-11-10T02:12:00+02:00",
        "hookStatus": "ok",
        "setup": {
            "classes": 2, "classesDelta": 0,
            "learnersEnrolled": 6, "learnersRegisteredDelta": 0, "teachersDelta": 0,
            "admin": {"total": 1, "beyondSeed": 0},
            "teacher": {"total": 1, "beyondSeed": 0},
            "learner": {"total": 8, "beyondSeed": 8},
        },
        "signins": {
            "learner": {"users": 4, "sessions": 4, "minutes": 10},
            "coach": {"users": 1, "sessions": 1, "minutes": 5},
            "admin": {"users": 1, "sessions": 1, "minutes": 2},
        },
        "guest": {"visits": 0, "seconds": 0},
        "teaching": {
            "lessonsCreated": 1, "lessonsVisible": 1,
            "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0,
        },
        "content": [],
        "flags": [],
    }
    nc = {
        "schema": "idea-usage-day/1",
        "engine": engine,
        "day": "2026-11-09",
        "app": "nextcloud",
        "instance": "nextcloud-a",
        "name": "Nextcloud",
        "demo": False,
        "listed": True,
        "clock": {"synced": True, "correctedBoots": 0},
        "collectedAt": "2026-11-10T02:13:00+02:00",
        "hookStatus": "ok",
        "setup": {
            "admin": {"total": 1, "beyondSeed": 0},
            "teacher": {"total": 2, "beyondSeed": 1},
            "learner": {"total": 3, "beyondSeed": 2},
            "otherGroups": {},
        },
        "logins": {
            "admin": {"total": 1, "beyondSeed": 0},
            "teacher": {"total": 1, "beyondSeed": 0},
            "learner": {"total": 0, "beyondSeed": 0},
        },
        "office": {
            "opens": 3, "distinctDocuments": 1, "read": 1, "edit": 2,
            "estimatedMinutes": 15,
            "byGroup": {"admin": 0, "teacher": 2, "learner": 1},
            "mime": {"text": 3, "sheet": 0, "slides": 0},
        },
        "appsOpened": {"files": 4, "richdocuments": 3},
        "workflows": {
            "worksheetShares": 1, "editShares": 0,
            "fileDropLinks": 0, "fileDropUploads": 2, "schoolFilesShares": 0,
        },
    }
    stub = {
        "schema": "idea-usage-day/1",
        "engine": engine,
        "day": "2026-11-09",
        "app": "kolibri",
        "instance": "unlisted-old",
        "name": "old-kolibri",
        "demo": False,
        "listed": False,
        "clock": {"synced": True, "correctedBoots": 0},
        "collectedAt": "2026-11-10T02:14:00+02:00",
        "hookStatus": "unlisted-no-hook",
    }
    presence = presence_payload(engine, "2026-11-09T08:00:00+02:00", "boot-1", 3600)
    presence2 = presence_payload(engine, "2026-11-09T12:00:00+02:00", "boot-1", 3600 + 4 * 3600)
    # Four-state week (2026-11-02): same-boot on, synced reboot off, then an
    # unsynced sample so the gap before 2026-11-09 stays gapUnknown (not off).
    four_on_a = presence_payload(engine, "2026-11-03T08:00:00+02:00", "boot-week2-a", 3600)
    four_on_b = presence_payload(engine, "2026-11-03T14:00:00+02:00", "boot-week2-a", 3600 + 6 * 3600)
    four_reboot = presence_payload(engine, "2026-11-04T07:00:00+02:00", "boot-week2-b", 600, synced=True)
    four_isolate = presence_payload(engine, "2026-11-04T07:10:00+02:00", "boot-week2-gap", 60, synced=False)
    day_four = dict(day_ok)
    day_four["day"] = FOUR_STATE_WEEK
    day_four["collectedAt"] = "2026-11-03T02:12:00+02:00"
    return {
        "presence": [
            {"type": "presence", "day": "2026-11-03", "payload": four_on_a},
            {"type": "presence", "day": "2026-11-03", "payload": four_on_b},
            {"type": "presence", "day": "2026-11-04", "payload": four_reboot},
            {"type": "presence", "day": "2026-11-04", "payload": four_isolate},
            {"type": "presence", "day": "2026-11-09", "payload": presence},
            {"type": "presence", "day": "2026-11-09", "payload": presence2},
        ],
        "days": [
            {"type": "day", "day": FOUR_STATE_WEEK, "instance": "kolibri-a", "payload": day_four},
            {"type": "day", "day": "2026-11-09", "instance": "kolibri-a", "payload": day_ok},
            {"type": "day", "day": "2026-11-09", "instance": "nextcloud-a", "payload": nc},
            {"type": "day", "day": "2026-11-09", "instance": "unlisted-old", "payload": stub},
        ],
        "samples": [],
        "end": {"type": "end", "counts": {"day": 4, "sample": 0, "presence": 6}, "errors": 0},
    }


def write_registry(path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"kits": [{
            "engine": "happy-zebra",
            "tailscaleName": "happy-zebra",
            "school": "Nharira",
            "deploymentId": "dep-nharira",
            "timezone": "Africa/Harare",
            "note": "own apps + Demo",
        }]}, fh)


def install_fixture(conn, registry_path):
    """Load the shared API fixture, including the four-state presence week."""
    write_registry(registry_path)
    db.load_registry(conn, registry_path)
    store_export(conn, "happy-zebra", export_for(), "2026-11-10T13:40:00+01:00", "dep-nharira")
    conn.execute(
        "INSERT INTO collector_gaps(start, end, reason) VALUES (?, ?, ?)",
        (COLLECTOR_GAP["start"], COLLECTOR_GAP["end"], COLLECTOR_GAP["reason"]),
    )
    conn.commit()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "usage.sqlite")
        self.conn = db.connect(self.db_path)
        registry = os.path.join(self.tmp, "registry.json")
        install_fixture(self.conn, registry)
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

    def test_health_no_auth(self):
        status, payload = self.call("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("ok", json.dumps(payload))

    def test_session_unauthenticated(self):
        status, payload = self.call("GET", "/api/v1/session")
        self.assertEqual(status, 200)
        self.assertFalse(payload["authenticated"])

    def test_kits_requires_auth(self):
        status, payload = self.call("GET", "/api/v1/kits")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_bad_login(self):
        status, payload = self.call("POST", "/api/v1/session", {"username": "admin", "password": "nope"})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "unauthorized")

    def test_non_monday(self):
        self.login()
        status, payload = self.call("GET", "/api/v1/weeks/2026-11-10/overview")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "validation")

    def test_overview_and_school_week(self):
        self.login()
        status, meta = self.call("GET", "/api/v1/meta")
        self.assertEqual(status, 200)
        self.assertEqual(meta["schema"], "idea-usage-api/1")
        self.assertEqual(meta["staleAfterHours"], 48)
        self.assertEqual(meta["hourlyChartMinWeeklyViews"], 20)
        self.assertFalse(meta["thresholdsConfigured"])

        status, kits = self.call("GET", "/api/v1/kits")
        self.assertEqual(status, 200)
        self.assertEqual(kits["kits"][0]["engine"], "happy-zebra")
        self.assertEqual(kits["kits"][0]["lastPulled"], "2026-11-10T13:40:00+01:00")
        self.assertTrue(kits["kits"][0]["monitoringEnabled"])

        status, overview = self.call("GET", "/api/v1/weeks/%s/overview" % WEEK)
        self.assertEqual(status, 200, overview)
        self.assertEqual(overview["weekEnd"], "2026-11-13")
        card = overview["cards"][0]
        self.assertTrue(card["hasUsageData"])
        self.assertTrue(card["monitoringEnabled"])
        self.assertEqual(card["headlines"]["classes"], 2)
        status, weeks = self.call("GET", "/api/v1/weeks")
        self.assertEqual(status, 200)
        self.assertEqual(weeks["currentWeekStart"], WEEK)
        self.assertEqual(weeks["todayWeekStart"], "2026-11-09")
        self.assertTrue(weeks["currentWeekHasData"])
        self.assertEqual(meta["todayWeekStart"], "2026-11-09")
        self.assertTrue(meta["currentWeekHasData"])
        self.assertEqual(card["scorecard"]["setup"]["classes"], 2)
        self.assertEqual(card["scorecard"]["nextcloud"]["fileDropUploads"], 2)
        self.assertEqual(card["scorecard"]["nextcloud"]["fileDropLinks"], 0)
        self.assertEqual(card["scorecard"]["nextcloud"]["officeOpens"], 3)
        self.assertEqual(card["scorecard"]["nextcloud"]["officeEdit"], 2)
        self.assertEqual(card["scorecard"]["setup"]["nextcloudTeacherBeyondSeed"], 1)
        self.assertEqual(card["scorecard"]["setup"]["nextcloudLearnerBeyondSeed"], 2)
        self.assertNotIn("fileDrops", card["scorecard"]["nextcloud"])
        self.assertNotIn("documentsCreatedOrEditedTeachers", card["scorecard"]["nextcloud"])

        status, school = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira" % WEEK)
        self.assertEqual(status, 200, school)
        self.assertEqual(school["census"]["classes"], 2)
        self.assertTrue(school["monitoringEnabled"])
        self.assertEqual(school["timezone"]["timeZone"], "Africa/Harare")
        self.assertTrue(school["clockTrusted"])
        self.assertNotIn("clockTrustworthy", school)
        states = {s["state"] for s in school["presence"]["segments"]}
        self.assertTrue(states.issubset({"on", "off", "gapUnknown", "collectorGap"}))
        self.assertIn("on", states)
        segs = school["presence"]["segments"]
        self.assertTrue(segs)
        self.assertEqual(segs[0]["start"], "2026-11-09T00:00:00+02:00")
        self.assertEqual(segs[-1]["end"], "2026-11-14T00:00:00+02:00")
        from src.presence import parse_ts
        total = sum((parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds() for s in segs)
        self.assertEqual(total, 5 * 86400)
        for prev, nxt in zip(segs, segs[1:]):
            self.assertEqual(parse_ts(prev["end"]), parse_ts(nxt["start"]))
        self.assertEqual(school["presence"]["summary"], "On 1 of 5 school days, 4 h in school hours")
        self.assertIsNot(school["presence"]["summary"], "")

        status, kolibri = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira/kolibri" % WEEK)
        inst = kolibri["instances"][0]
        self.assertEqual(inst["instance"], "kolibri-a")
        self.assertEqual(inst["instanceId"], "kolibri-a")
        self.assertTrue(kolibri["clockTrusted"])
        self.assertEqual(inst["hookStatus"], "ok")
        self.assertIn("clock", inst)
        self.assertIn("collectedAt", inst)
        self.assertTrue(inst["listed"])

        status, nc = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira/nextcloud" % WEEK)
        n = nc["instances"][0]
        self.assertTrue(nc["clockTrusted"])
        self.assertEqual(n["instanceId"], "nextcloud-a")
        self.assertEqual(n["office"]["byGroup"]["teacher"], 2)
        self.assertEqual(n["logins"]["teacher"], {"total": 1, "beyondSeed": 0})
        self.assertEqual(n["setup"]["teacher"], {"total": 2, "beyondSeed": 1})
        self.assertEqual(n["appsOpened"]["files"], 4)
        self.assertEqual(n["workflows"]["fileDropUploads"], 2)

        status, discovered = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira/instances" % WEEK)
        ids = {i["instance"]: i for i in discovered["instances"]}
        self.assertEqual(ids["unlisted-old"]["hookStatus"], "unlisted-no-hook")
        self.assertFalse(ids["unlisted-old"]["listed"])
        self.assertIsNone(ids["kolibri-a"]["port"])

    def test_uplink_uses_offset_aware_week_bounds(self):
        self.login()
        rows = [
            ("2026-11-08T21:00:00Z", False),       # Sun 23:00 +02 — before the week
            ("2026-11-08T23:00:00Z", True),        # Mon 01:00 +02 — inside
            ("2026-11-09T00:30:00+02:00", True),   # Mon morning kit-local — inside
            ("2026-11-13T21:30:00+02:00", True),   # Friday evening — inside
            ("2026-11-13T22:30:00Z", False),       # Sat 00:30 +02 — after weekEnd
        ]
        for ts, _keep in rows:
            self.conn.execute(
                "INSERT INTO uplink_samples(engine, timestamp, online, last_seen, via, latency_ms) VALUES (?, ?, 1, NULL, 'direct', NULL)",
                ("happy-zebra", ts),
            )
            self.conn.execute(
                "INSERT INTO uplink_transitions(engine, timestamp, from_state, to_state) VALUES (?, ?, 'offline', 'online')",
                ("happy-zebra", ts),
            )
        self.conn.commit()
        status, payload = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira/uplink" % WEEK)
        self.assertEqual(status, 200, payload)
        got = {item["timestamp"] for item in payload["samples"]}
        want = {ts for ts, keep in rows if keep}
        drop = {ts for ts, keep in rows if not keep}
        self.assertEqual(got, want)
        self.assertTrue(drop.isdisjoint(got))
        self.assertEqual({item["timestamp"] for item in payload["transitions"]}, want)

    def test_current_week_is_latest_with_stored_data(self):
        self.login()
        self.conn.execute("DELETE FROM daily_summaries")
        self.conn.execute("DELETE FROM presence_days")
        self.conn.execute(
            """INSERT INTO daily_summaries(engine, deployment_id, day, instance, app, name, demo, listed, hook_status, skip_reason, payload, pulled_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, 1, 'ok', NULL, '{}', ?)""",
            ("happy-zebra", "dep-nharira", "2026-11-03", "kolibri-a", "kolibri", "Kolibri", "2026-11-03T18:00:00+02:00"),
        )
        self.conn.commit()
        status, weeks = self.call("GET", "/api/v1/weeks")
        self.assertEqual(status, 200, weeks)
        self.assertEqual(weeks["currentWeekStart"], "2026-11-02")
        self.assertEqual(weeks["todayWeekStart"], "2026-11-09")
        self.assertTrue(weeks["currentWeekHasData"])
        status, meta = self.call("GET", "/api/v1/meta")
        self.assertEqual(meta["todayWeekStart"], "2026-11-09")
        self.assertTrue(meta["currentWeekHasData"])

    def test_four_state_presence_week(self):
        self.login()
        status, school = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira" % FOUR_STATE_WEEK)
        self.assertEqual(status, 200, school)
        segs = school["presence"]["segments"]
        states = {item["state"] for item in segs}
        self.assertEqual(states, {"on", "off", "collectorGap", "gapUnknown"})
        from src.presence import parse_ts, week_bounds
        start, end = week_bounds(FOUR_STATE_WEEK, school["presence"]["timezone"]["utcOffset"])
        self.assertEqual(parse_ts(segs[0]["start"]), start)
        self.assertEqual(parse_ts(segs[-1]["end"]), end)
        total = sum((parse_ts(item["end"]) - parse_ts(item["start"])).total_seconds() for item in segs)
        self.assertEqual(total, 5 * 86400)
        for prev, nxt in zip(segs, segs[1:]):
            self.assertEqual(parse_ts(prev["end"]), parse_ts(nxt["start"]))
        off = [item for item in segs if item["state"] == "off"]
        self.assertTrue(off)
        self.assertTrue(all(item["lengthKnown"] for item in off))
        gap = [item for item in segs if item["state"] == "collectorGap"]
        self.assertEqual(len(gap), 1)
        self.assertEqual(gap[0]["start"], COLLECTOR_GAP["start"])
        self.assertEqual(gap[0]["end"], COLLECTOR_GAP["end"])
        status, pres = self.call("GET", "/api/v1/weeks/%s/schools/dep-nharira/presence" % FOUR_STATE_WEEK)
        self.assertEqual(status, 200, pres)
        self.assertEqual({item["state"] for item in pres["segments"]}, states)
        self.assertEqual(sum((parse_ts(item["end"]) - parse_ts(item["start"])).total_seconds() for item in pres["segments"]), 5 * 86400)

    def test_overview_monitoring_and_never_enabled_kit(self):
        self.conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('idea04', 'idea04', 'Pool Pi 4', 'dep-idea04', 'Europe/Brussels',
                       0, NULL, '', ?)""",
            (db.now_rfc3339(),),
        )
        # Production-like: a first-connect rejected row plus later disabled polls.
        self.conn.execute(
            """INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, since_day, message)
               VALUES ('idea04', '2026-11-11T00:54:03+01:00', '2026-11-11T00:54:03+01:00',
                       0, 'rejected', '2026-10-28', 'exit 10 with unexpected stderr')"""
        )
        self.conn.execute(
            """INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, since_day, message)
               VALUES ('idea04', '2026-11-11T00:54:17+01:00', '2026-11-11T00:54:17+01:00',
                       1, 'disabled', '2026-10-28', 'disabled')"""
        )
        # Sidecar outage inside this school week. Must not become collectorGap
        # on a never-enabled kit (and with utcOffset +00:00 it would also have
        # been drawn as late Tuesday 23:48).
        self.conn.execute(
            "INSERT INTO collector_gaps(start, end, reason) VALUES (?, ?, ?)",
            ("2026-11-11T00:48:00+01:00", "2026-11-11T00:54:00+01:00", "sidecar-offline"),
        )
        self.conn.commit()
        self.login()
        status, overview = self.call("GET", "/api/v1/weeks/%s/overview" % WEEK)
        self.assertEqual(status, 200, overview)
        by_engine = {card["engine"]: card for card in overview["cards"]}
        self.assertTrue(by_engine["happy-zebra"]["monitoringEnabled"])
        self.assertFalse(by_engine["idea04"]["monitoringEnabled"])
        status, school = self.call("GET", "/api/v1/weeks/%s/schools/dep-idea04" % WEEK)
        self.assertEqual(status, 200, school)
        self.assertFalse(school["monitoringEnabled"])
        self.assertEqual(school["timezone"]["timeZone"], "Europe/Brussels")
        self.assertEqual(school["timezone"]["utcOffset"], "+01:00")
        status, pres = self.call("GET", "/api/v1/weeks/%s/schools/dep-idea04/presence" % WEEK)
        self.assertEqual(status, 200, pres)
        self.assertEqual(pres["timezone"]["utcOffset"], "+01:00")
        self.assertEqual(pres["timezone"]["timeZone"], "Europe/Brussels")
        states = {item["state"] for item in pres["segments"]}
        self.assertEqual(states, {"gapUnknown"})
        self.assertNotIn("collectorGap", states)
        self.assertEqual(pres["segments"][0]["start"], "2026-11-09T00:00:00+01:00")
        self.assertEqual(pres["segments"][-1]["end"], "2026-11-14T00:00:00+01:00")
        from src.presence import parse_ts
        total = sum((parse_ts(s["end"]) - parse_ts(s["start"])).total_seconds() for s in pres["segments"])
        self.assertEqual(total, 5 * 86400)

    def test_disabled_after_enabled_hides_later_collector_gaps(self):
        self.conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('was-on', 'was-on', 'Toggled', 'dep-toggled', 'Africa/Harare',
                       0, '2026-11-03T18:00:00+02:00', '', ?)""",
            (db.now_rfc3339(),),
        )
        self.conn.execute(
            """INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, since_day, message)
               VALUES ('was-on', '2026-11-03T08:00:00+02:00', '2026-11-03T08:00:00+02:00',
                       1, 'success', '2026-10-20', 'ok')"""
        )
        self.conn.execute(
            """INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, since_day, message)
               VALUES ('was-on', '2026-11-04T12:00:00+02:00', '2026-11-04T12:00:00+02:00',
                       1, 'disabled', '2026-10-20', 'disabled')"""
        )
        self.conn.execute(
            "INSERT INTO collector_gaps(start, end, reason) VALUES (?, ?, ?)",
            ("2026-11-02T12:00:00+02:00", "2026-11-02T14:00:00+02:00", "before-enable"),
        )
        self.conn.execute(
            "INSERT INTO collector_gaps(start, end, reason) VALUES (?, ?, ?)",
            ("2026-11-03T10:00:00+02:00", "2026-11-03T12:00:00+02:00", "while-on"),
        )
        self.conn.commit()
        self.login()
        status, pres = self.call("GET", "/api/v1/weeks/%s/schools/dep-toggled/presence" % FOUR_STATE_WEEK)
        self.assertEqual(status, 200, pres)
        gaps = [item for item in pres["segments"] if item["state"] == "collectorGap"]
        self.assertEqual(len(gaps), 1, gaps)
        self.assertEqual(gaps[0]["start"], "2026-11-03T10:00:00+02:00")
        self.assertEqual(gaps[0]["end"], "2026-11-03T12:00:00+02:00")
        # The fixture's Nov 5 sidecar gap and the pre-enable gap must not appear.
        self.assertFalse(any(item["start"].startswith("2026-11-02T12:") for item in gaps))
        self.assertFalse(any(item["start"].startswith("2026-11-05T") for item in gaps))

    def test_help_event(self):
        self.login()
        status, created = self.call("POST", "/api/v1/schools/dep-nharira/help-events", {
            "offeredOn": "2026-11-10",
            "tutorialChapters": ["3.3"],
            "note": "Visited",
        })
        self.assertEqual(status, 201, created)
        self.assertEqual(created["offeredOn"], "2026-11-10")
        self.assertEqual(created["createdBy"], "admin")
        status, listing = self.call("GET", "/api/v1/schools/dep-nharira/help-events")
        self.assertEqual(status, 200)
        self.assertEqual(len(listing["events"]), 1)
        self.assertTrue(listing["weeklyTrend"])


if __name__ == "__main__":
    unittest.main()
