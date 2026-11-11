import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src.aggregate import (
    clocks_trusted,
    discovered_instance,
    group_by_instance,
    help_suggestions_for,
    instance_envelope,
    is_monday,
    kolibri_week,
    nextcloud_week,
    kiwix_week,
    presence_summary,
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
        self.assertIsNone(week["clock"])
        self.assertTrue(clocks_trusted([week]))

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
        self.assertEqual(card["nextcloud"]["officeOpensTeacherLearner"], 7)
        self.assertEqual(card["nextcloud"]["officeOpensAdmin"], 0)
        self.assertEqual(card["nextcloud"]["officeDistinctDocuments"], 2)
        self.assertEqual(card["nextcloud"]["officeEdit"], 6)
        self.assertNotIn("fileDrops", card["nextcloud"])
        self.assertNotIn("documentsCreatedOrEditedTeachers", card["nextcloud"])

    def test_office_opens_split_excludes_admin_and_nulls_missing_by_group(self):
        from src.thresholds import AMBER, GREEN, line_tones, nextcloud_actions

        def nc_row(day, office):
            return row(day, "nc-a", "nextcloud", {
                "name": "Nextcloud",
                "setup": {
                    "admin": {"total": 1, "beyondSeed": 0},
                    "teacher": {"total": 1, "beyondSeed": 1},
                    "learner": {"total": 1, "beyondSeed": 1},
                    "otherGroups": {},
                },
                "office": office,
                "workflows": {
                    "worksheetShares": 0, "editShares": 0,
                    "fileDropLinks": 0, "fileDropUploads": 0, "schoolFilesShares": 0,
                },
            })

        split = nextcloud_week([nc_row("2026-11-09", {
            "opens": 6, "distinctDocuments": 2, "read": 1, "edit": 2,
            "byGroup": {"admin": 4, "teacher": 1, "learner": 1},
            "mime": {"text": 6, "sheet": 0, "slides": 0},
        })])
        card = scorecard_from_weeks([], [split], [], [], "2026-11-09")
        self.assertEqual(card["nextcloud"]["officeOpens"], 6)
        self.assertEqual(card["nextcloud"]["officeOpensTeacherLearner"], 2)
        self.assertEqual(card["nextcloud"]["officeOpensAdmin"], 4)
        self.assertEqual(nextcloud_actions(card), 2)
        self.assertEqual(line_tones(card)["nextcloud"], GREEN)

        admin_only = nextcloud_week([nc_row("2026-11-09", {
            "opens": 5, "distinctDocuments": 1, "read": 0, "edit": 0,
            "byGroup": {"admin": 5, "teacher": 0, "learner": 0},
            "mime": {"text": 5, "sheet": 0, "slides": 0},
        })])
        card = scorecard_from_weeks([], [admin_only], [], [], "2026-11-09")
        self.assertEqual(card["nextcloud"]["officeOpens"], 5)
        self.assertEqual(card["nextcloud"]["officeOpensTeacherLearner"], 0)
        self.assertEqual(card["nextcloud"]["officeOpensAdmin"], 5)
        self.assertEqual(nextcloud_actions(card), 0)
        self.assertEqual(line_tones(card)["nextcloud"], AMBER)

        old = nextcloud_week([nc_row("2026-11-09", {
            "opens": 6, "distinctDocuments": 1, "read": 0, "edit": 0,
            "mime": {"text": 6, "sheet": 0, "slides": 0},
        })])
        self.assertEqual(old["office"]["opens"], 6)
        self.assertEqual(old["office"]["byGroup"], {"admin": 0, "teacher": 0, "learner": 0})
        card = scorecard_from_weeks([], [old], [], [], "2026-11-09")
        self.assertEqual(card["nextcloud"]["officeOpens"], 6)
        self.assertIsNone(card["nextcloud"]["officeOpensTeacherLearner"])
        self.assertIsNone(card["nextcloud"]["officeOpensAdmin"])
        self.assertEqual(nextcloud_actions(card), 0)
        self.assertEqual(line_tones(card)["nextcloud"], AMBER)

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


    def test_office_distinct_documents_sums_across_own_instances(self):
        def nc(instance, distinct, demo=False):
            return nextcloud_week([row("2026-11-09", instance, "nextcloud", {
                "name": "Nextcloud",
                "demo": demo,
                "setup": {
                    "admin": {"total": 1, "beyondSeed": 0},
                    "teacher": {"total": 1, "beyondSeed": 0},
                    "learner": {"total": 1, "beyondSeed": 0},
                    "otherGroups": {},
                },
                "logins": {
                    "admin": {"total": 0, "beyondSeed": 0},
                    "teacher": {"total": 0, "beyondSeed": 0},
                    "learner": {"total": 0, "beyondSeed": 0},
                },
                "office": {
                    "opens": distinct, "distinctDocuments": distinct,
                    "read": 0, "edit": distinct,
                    "estimatedMinutes": 1,
                    "byGroup": {"admin": 0, "teacher": distinct, "learner": 0},
                    "mime": {"text": distinct, "sheet": 0, "slides": 0},
                },
                "workflows": {
                    "worksheetShares": 0, "editShares": 0,
                    "fileDropLinks": 0, "fileDropUploads": 0, "schoolFilesShares": 0,
                },
            })])

        own_a = nc("nc-a", 2)
        own_b = nc("nc-b", 3)
        demo = nc("nc-demo", 99, demo=True)
        card = scorecard_from_weeks([], [own_a, own_b, demo], [], [], "2026-11-09")
        self.assertEqual(card["nextcloud"]["officeDistinctDocuments"], 5)

    def test_presence_summary_sentence_or_none(self):
        days = [
            {"day": "2026-11-09", "schoolHoursOnMinutes": 540},
            {"day": "2026-11-10", "schoolHoursOnMinutes": 480},
            {"day": "2026-11-11", "schoolHoursOnMinutes": 420},
            {"day": "2026-11-12", "schoolHoursOnMinutes": 420},
            {"day": "2026-11-13", "schoolHoursOnMinutes": 0},
        ]
        self.assertEqual(
            presence_summary(days, "2026-11-09"),
            "On 4 of 5 school days, 31 h in school hours",
        )
        self.assertIsNone(presence_summary([], "2026-11-09"))

    def test_stub_clock_does_not_taint_week(self):
        """no-hook / unlisted-no-hook / skipped stubs: clock is null, week trusted."""
        kit_rows = []
        for hook, instance, extra in (
            ("no-hook", "usage-dashboard", {"collectedAt": "2026-11-11T00:51:34+01:00"}),
            ("unlisted-no-hook", "unlisted-old", {"collectedAt": "2026-11-11T00:51:34+01:00"}),
            ("skipped", "updtest-stale", {"skipReason": "backup", "collectedAt": "2026-11-11T00:51:34+01:00"}),
        ):
            payload = {
                "name": instance,
                "clock": {"synced": False, "correctedBoots": 0},
                "hookStatus": hook,
            }
            payload.update(extra)
            kit_rows.append(row("2026-10-28", instance, "other", payload, hook=hook))
        for item in kit_rows:
            env = instance_envelope([item])
            self.assertIsNone(env["clock"], env)
            self.assertTrue(clocks_trusted([discovered_instance([item])]))
        self.assertTrue(clocks_trusted([discovered_instance([item]) for item in kit_rows]))

    def test_ok_unsynced_clock_taints_week(self):
        rows = [row("2026-11-09", "kolibri-a", "kolibri", {
            "name": "Kolibri",
            "clock": {"synced": False, "correctedBoots": 1},
            "setup": {"classes": 1},
            "signins": {"learner": {"users": 0, "sessions": 0, "minutes": 0},
                        "coach": {"users": 0, "sessions": 0, "minutes": 0},
                        "admin": {"users": 0, "sessions": 0, "minutes": 0}},
            "guest": {"visits": 0, "seconds": 0},
            "teaching": {"lessonsCreated": 0, "lessonsVisible": 0,
                         "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0},
            "content": [],
        })]
        week = kolibri_week(rows)
        self.assertFalse(week["clock"]["synced"])
        self.assertFalse(clocks_trusted([week]))

    def test_single_off_week_does_not_offer_help(self):
        kit = {
            "engine": "happy-zebra",
            "school": "Nharira",
            "deployment_id": "dep-nharira",
            "monitoring_enabled": 1,
            "last_pulled": "2026-11-10T13:40:00+01:00",
        }
        card = {"hasUsageData": True}
        outside = [{
            "day": "2026-11-09",
            "onMinutes": 180,
            "schoolHoursOnMinutes": 0,
            "boots": 1,
            "longestGapMinutes": 0,
            "lengthKnown": True,
        }]
        scorecard = scorecard_from_weeks([], [], [], outside, "2026-11-09")
        self.assertEqual(scorecard["available"]["schoolDaysOn"], 0)
        self.assertEqual(scorecard["available"]["schoolHoursOnMinutes"], 0)
        self.assertIsNone(help_suggestions_for(card, kit, scorecard, outside, week_start="2026-11-09"))

        off = [{
            "day": "2026-11-09",
            "onMinutes": 0,
            "schoolHoursOnMinutes": 0,
            "boots": 0,
            "longestGapMinutes": 0,
            "lengthKnown": True,
        }]
        scorecard = scorecard_from_weeks([], [], [], off, "2026-11-09")
        self.assertIsNone(help_suggestions_for(card, kit, scorecard, off, week_start="2026-11-09"))


if __name__ == "__main__":
    unittest.main()
