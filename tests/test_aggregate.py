import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src.aggregate import (
    group_by_instance,
    is_monday,
    kolibri_week,
    nextcloud_week,
    kiwix_week,
    scorecard_from_weeks,
)


def row(day, instance, app, payload, hook="ok"):
    payload = dict(payload)
    payload.setdefault("schema", "idea-usage-day/1")
    payload.setdefault("day", day)
    payload.setdefault("app", app)
    payload.setdefault("instance", instance)
    payload.setdefault("hookStatus", hook)
    payload.setdefault("listed", True)
    payload.setdefault("demo", False)
    payload.setdefault("clock", {"synced": True, "correctedBoots": 0})
    return {
        "day": day,
        "instance": instance,
        "app": app,
        "hook_status": hook,
        "listed": 1,
        "payload": json.dumps(payload),
    }


class AggregateTests(unittest.TestCase):
    def test_monday(self):
        self.assertTrue(is_monday("2026-11-09"))
        self.assertFalse(is_monday("2026-11-10"))

    def test_census_from_last_ok_not_summed(self):
        rows = [
            row("2026-11-09", "kolibri-a", "kolibri", {
                "name": "Kolibri",
                "setup": {"classes": 1, "classesDelta": 1, "learnersRegistered": 10,
                          "learnersRegisteredDelta": 2, "learnersEnrolled": 8,
                          "teachers": 1, "teachersDelta": 0, "admins": 1},
                "signins": {"learner": {"users": 4, "sessions": 5, "minutes": 20},
                            "coach": {"users": 1, "sessions": 1, "minutes": 10},
                            "admin": {"users": 1, "sessions": 1, "minutes": 5}},
                "guest": {"visits": 0, "seconds": 0},
                "teaching": {"lessonsCreated": 1, "lessonsVisible": 1,
                             "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0},
                "content": [],
            }),
            row("2026-11-10", "kolibri-a", "kolibri", {
                "name": "Kolibri",
                "setup": {"classes": 2, "classesDelta": 1, "learnersRegistered": 12,
                          "learnersRegisteredDelta": 2, "learnersEnrolled": 9,
                          "teachers": 2, "teachersDelta": 1, "admins": 1},
                "signins": {"learner": {"users": 6, "sessions": 7, "minutes": 30},
                            "coach": {"users": 1, "sessions": 2, "minutes": 8},
                            "admin": {"users": 1, "sessions": 0, "minutes": 0}},
                "guest": {"visits": 1, "seconds": 120},
                "teaching": {"lessonsCreated": 2, "lessonsVisible": 2,
                             "quizzesCreated": 1, "quizzesStarted": 1, "quizzesEnded": 0},
                "content": [{"channel": "Maths", "title": "Fractions", "kind": "video",
                             "role": "learner", "visits": 3, "seconds": 60, "completions": 0,
                             "assigned": True}],
                "clock": {"synced": False, "correctedBoots": 1},
            }),
        ]
        week = kolibri_week(rows)
        self.assertEqual(week["instance"], "kolibri-a")
        self.assertEqual(week["instanceId"], "kolibri-a")
        self.assertEqual(week["setup"]["classes"], 2)  # last ok, not 1+2
        self.assertEqual(week["setup"]["classesDelta"], 1)  # last ok day's delta, not summed
        self.assertEqual(week["signins"]["learner"]["sessions"], 12)
        self.assertEqual(week["teaching"]["lessonsCreated"], 3)
        self.assertEqual(week["teaching"]["lessonsVisible"], 2)
        self.assertFalse(week["clock"]["synced"])  # any unsynced day taints the week
        self.assertEqual(week["hookStatus"], "ok")

    def test_kolibri_rolecount_setup_maps_to_census(self):
        rows = [row("2026-11-09", "kolibri-a", "kolibri", {
            "name": "Kolibri",
            "setup": {
                "classes": 2, "classesDelta": 0,
                "learnersEnrolled": 6, "learnersRegisteredDelta": 1, "teachersDelta": 0,
                "admin": {"total": 1, "beyondSeed": 0},
                "teacher": {"total": 1, "beyondSeed": 0},
                "learner": {"total": 8, "beyondSeed": 8},
            },
            "signins": {"learner": {"users": 4, "sessions": 4, "minutes": 10},
                        "coach": {"users": 1, "sessions": 1, "minutes": 5},
                        "admin": {"users": 0, "sessions": 0, "minutes": 0}},
            "guest": {"visits": 0, "seconds": 0},
            "teaching": {"lessonsCreated": 0, "lessonsVisible": 0,
                         "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0},
            "content": [],
        })]
        week = kolibri_week(rows)
        self.assertEqual(week["setup"]["learnersRegistered"], 8)
        self.assertEqual(week["setup"]["teachers"], 1)
        self.assertEqual(week["setup"]["admins"], 1)
        self.assertNotIn("learner", week["setup"])
        card = scorecard_from_weeks([week], [], [], [], "2026-11-09")
        self.assertEqual(card["setup"]["learnersRegistered"], 8)
        self.assertEqual(card["setup"]["teachers"], 1)

    def test_stub_payloads_null(self):
        rows = [row("2026-11-09", "kolibri-a", "kolibri", {
            "name": "Kolibri", "hookStatus": "failed",
        }, hook="failed")]
        week = kolibri_week(rows)
        self.assertIsNone(week["setup"])
        self.assertEqual(week["hookStatus"], "failed")

    def test_nextcloud_engine_shapes_and_singular_roles(self):
        rows = [
            row("2026-11-09", "nc-a", "nextcloud", {
                "name": "Nextcloud",
                "setup": {
                    "admin": {"total": 1, "beyondSeed": 0},
                    "teacher": {"total": 2, "beyondSeed": 1},
                    "learner": {"total": 3, "beyondSeed": 2},
                    "otherGroups": {"Grade 5": 2},
                },
                "logins": {
                    "admin": {"total": 1, "beyondSeed": 0},
                    "teacher": {"total": 1, "beyondSeed": 0},
                    "learner": {"total": 1, "beyondSeed": 1},
                },
                "office": {
                    "opens": 5, "distinctDocuments": 5, "read": 1, "edit": 4,
                    "estimatedMinutes": 15,
                    "byGroup": {"admin": 0, "teacher": 4, "learner": 1},
                    "mime": {"text": 3, "sheet": 2, "slides": 0},
                },
                "appsOpened": {"files": 10, "richdocuments": 5},
                "workflows": {
                    "worksheetShares": 1, "editShares": 1,
                    "fileDropLinks": 1, "fileDropUploads": 3, "schoolFilesShares": 0,
                },
            }),
            row("2026-11-10", "nc-a", "nextcloud", {
                "name": "Nextcloud",
                "setup": {
                    "admin": {"total": 1, "beyondSeed": 0},
                    "teacher": {"total": 3, "beyondSeed": 2},
                    "learner": {"total": 4, "beyondSeed": 3},
                    "otherGroups": {"Grade 5": 2},
                },
                "logins": {
                    "admin": {"total": 0, "beyondSeed": 0},
                    "teacher": {"total": 2, "beyondSeed": 1},
                    "learner": {"total": 1, "beyondSeed": 1},
                },
                "office": {
                    "opens": 2, "distinctDocuments": 2, "read": 0, "edit": 2,
                    "estimatedMinutes": 8,
                    "byGroup": {"admin": 0, "teacher": 2, "learner": 0},
                    "mime": {"text": 1, "sheet": 1, "slides": 0},
                },
                "appsOpened": {"files": 2},
                "workflows": {
                    "worksheetShares": 0, "editShares": 0,
                    "fileDropLinks": 0, "fileDropUploads": 1, "schoolFilesShares": 1,
                },
            }),
        ]
        week = nextcloud_week(rows)
        self.assertEqual(week["instance"], "nc-a")
        self.assertEqual(week["instanceId"], "nc-a")
        self.assertEqual(week["setup"]["teacher"], {"total": 3, "beyondSeed": 2})
        self.assertEqual(week["setup"]["learner"], {"total": 4, "beyondSeed": 3})
        self.assertEqual(week["setup"]["admin"], {"total": 1, "beyondSeed": 0})
        self.assertEqual(week["setup"]["otherGroups"]["Grade 5"], 2)
        self.assertNotIn("teachers", week["setup"])
        self.assertNotIn("learners", week["setup"])
        self.assertNotIn("teachersBeyondSeeds", week["setup"])
        self.assertEqual(week["logins"]["teacher"], {"total": 3, "beyondSeed": 1})
        self.assertEqual(week["logins"]["learner"], {"total": 2, "beyondSeed": 2})
        self.assertNotIn("teachers", week["logins"])
        self.assertEqual(week["office"]["byGroup"]["teacher"], 6)
        self.assertNotIn("teachers", week["office"]["byGroup"])
        self.assertEqual(week["office"]["opens"], 7)
        self.assertEqual(week["office"]["distinctDocuments"], 2)  # last ok day, not max or sum
        self.assertEqual(week["office"]["estimatedMinutes"], 23)
        self.assertEqual(week["appsOpened"]["files"], 12)
        self.assertEqual(week["workflows"]["fileDropUploads"], 4)
        self.assertEqual(week["workflows"]["schoolFilesShares"], 1)
        self.assertNotIn("fileDrops", week["workflows"])
        card = scorecard_from_weeks([], [week], [], [], "2026-11-09")
        self.assertEqual(card["setup"]["nextcloudTeacherBeyondSeed"], 2)
        self.assertEqual(card["setup"]["nextcloudLearnerBeyondSeed"], 3)
        self.assertEqual(card["nextcloud"]["fileDropUploads"], 4)
        self.assertEqual(card["nextcloud"]["fileDropLinks"], 1)
        self.assertEqual(card["nextcloud"]["officeOpens"], 7)
        self.assertEqual(card["nextcloud"]["officeDistinctDocuments"], 2)
        self.assertEqual(card["nextcloud"]["officeEdit"], 6)
        self.assertNotIn("fileDrops", card["nextcloud"])
        self.assertNotIn("documentsCreatedOrEditedTeachers", card["nextcloud"])

    def test_nextcloud_missing_beyond_seed_is_null(self):
        rows = [row("2026-11-09", "nc-a", "nextcloud", {
            "name": "Nextcloud",
            "setup": {"admin": 1, "teachers": 3, "learners": 4, "otherGroups": {}},
            "logins": {"admin": {"users": 1}, "teacher": {"users": 2}, "learner": {"users": 1}},
            "office": {
                "opens": 1, "distinctDocuments": 1, "read": 0, "edit": 1,
                "byGroup": {"admin": 0, "teacher": 1, "learner": 0},
                "mime": {"text": 1, "sheet": 0, "slides": 0},
            },
            "workflows": {
                "worksheetShares": 0, "editShares": 0,
                "fileDropLinks": 0, "fileDropUploads": 0, "schoolFilesShares": 0,
            },
        })]
        week = nextcloud_week(rows)
        self.assertEqual(week["setup"]["teacher"], {"total": 3, "beyondSeed": None})
        self.assertEqual(week["logins"]["teacher"], {"total": 2, "beyondSeed": None})
        card = scorecard_from_weeks([], [week], [], [], "2026-11-09")
        self.assertIsNone(card["setup"]["nextcloudTeacherBeyondSeed"])
        self.assertIsNone(card["setup"]["nextcloudLearnerBeyondSeed"])

    def test_demo_not_in_own_scorecard(self):
        own = kolibri_week([row("2026-11-09", "k-own", "kolibri", {
            "name": "Kolibri",
            "setup": {"classes": 2, "classesDelta": 0, "learnersRegistered": 8,
                      "learnersRegisteredDelta": 0, "learnersEnrolled": 6,
                      "teachers": 1, "teachersDelta": 0, "admins": 1},
            "signins": {"learner": {"users": 4, "sessions": 4, "minutes": 10},
                        "coach": {"users": 1, "sessions": 1, "minutes": 5},
                        "admin": {"users": 0, "sessions": 0, "minutes": 0}},
            "guest": {"visits": 0, "seconds": 0},
            "teaching": {"lessonsCreated": 1, "lessonsVisible": 1,
                         "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0},
            "content": [],
        })])
        demo = kolibri_week([row("2026-11-09", "k-demo", "kolibri", {
            "name": "Kolibri Demo", "demo": True,
            "setup": {"classes": 9, "classesDelta": 0, "learnersRegistered": 99,
                      "learnersRegisteredDelta": 0, "learnersEnrolled": 99,
                      "teachers": 9, "teachersDelta": 0, "admins": 1},
            "signins": {"learner": {"users": 6, "sessions": 50, "minutes": 400},
                        "coach": {"users": 1, "sessions": 0, "minutes": 0},
                        "admin": {"users": 0, "sessions": 0, "minutes": 0}},
            "guest": {"visits": 0, "seconds": 0},
            "teaching": {"lessonsCreated": 8, "lessonsVisible": 8,
                         "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0},
            "content": [],
        })])
        self.assertTrue(demo["demo"])
        card = scorecard_from_weeks([own, demo], [], [], [], "2026-11-09")
        self.assertEqual(card["setup"]["classes"], 2)
        self.assertEqual(card["learnersOperate"]["learnerSessions"], 4)
        self.assertNotEqual(card["setup"]["classes"], 9)


if __name__ == "__main__":
    unittest.main()
