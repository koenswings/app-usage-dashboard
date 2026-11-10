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


WEEK = "2026-11-09"  # Monday


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
    presence = {
        "schema": "idea-usage-presence/1",
        "engine": engine,
        "ts": "2026-11-09T08:00:00+02:00",
        "bootId": "boot-1",
        "uptimeS": 3600,
        "ntpSynced": True,
        "engineUp": True,
        "instancesUp": ["kolibri-a"],
        "tempC": 50.0,
        "throttled": "0x0",
    }
    presence2 = dict(presence)
    presence2["ts"] = "2026-11-09T12:00:00+02:00"
    presence2["uptimeS"] = 3600 + 4 * 3600
    return {
        "presence": [
            {"type": "presence", "day": "2026-11-09", "payload": presence},
            {"type": "presence", "day": "2026-11-09", "payload": presence2},
        ],
        "days": [
            {"type": "day", "day": "2026-11-09", "instance": "kolibri-a", "payload": day_ok},
            {"type": "day", "day": "2026-11-09", "instance": "nextcloud-a", "payload": nc},
            {"type": "day", "day": "2026-11-09", "instance": "unlisted-old", "payload": stub},
        ],
        "samples": [],
        "end": {"type": "end", "counts": {"day": 3, "sample": 0, "presence": 2}, "errors": 0},
    }


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "usage.sqlite")
        self.conn = db.connect(self.db_path)
        registry = os.path.join(self.tmp, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump({"kits": [{
                "engine": "happy-zebra",
                "tailscaleName": "happy-zebra",
                "school": "Nharira",
                "deploymentId": "dep-nharira",
                "timezone": "Africa/Harare",
                "note": "own apps + Demo",
            }]}, fh)
        db.load_registry(self.conn, registry)
        store_export(self.conn, "happy-zebra", export_for(), "2026-11-10T13:40:00+01:00", "dep-nharira")
        self.conn.commit()
        os.environ["IDEA_USAGE_ADMIN_PASSWORD"] = "admin911!"
        os.environ["IDEA_USAGE_SESSION_SECRET"] = "test-secret"
        self.server = serve(self.conn, "127.0.0.1:18080")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:18080"
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
        self.assertEqual(card["headlines"]["classes"], 2)
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
        self.assertEqual(school["timezone"]["timeZone"], "Africa/Harare")
        self.assertTrue(school["clockTrusted"])
        self.assertNotIn("clockTrustworthy", school)
        states = {s["state"] for s in school["presence"]["segments"]}
        self.assertTrue(states.issubset({"on", "off", "gapUnknown", "collectorGap"}))
        self.assertIn("on", states)

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
