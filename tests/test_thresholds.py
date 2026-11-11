import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import db
from src.aggregate import empty_scorecard, help_status_for, help_suggestions_for
from src.thresholds import (
    AMBER,
    DEFAULTS,
    GREEN,
    GREY,
    ValidationError,
    amber_streak,
    apply_put,
    effective,
    line_tones,
    settings_payload,
    unused_streak,
    week_tone,
)


KIT = {
    "engine": "happy-zebra",
    "school": "Nharira",
    "deployment_id": "dep-nharira",
    "monitoring_enabled": 1,
    "last_pulled": "2026-11-10T13:40:00+01:00",
}


def amber_scorecard():
    return {
        "available": {
            "schoolDaysOn": 0,
            "schoolDaysExpected": 5,
            "schoolHoursOnMinutes": 0,
            "bootsPerSchoolDay": [0, 0, 0, 0, 0],
            "longestGapMinutes": 0,
        },
        "setup": {
            "classes": 0,
            "learnersRegistered": 0,
            "learnersEnrolled": 0,
            "teachers": 0,
            "admins": 0,
            "nextcloudTeacherBeyondSeed": None,
            "nextcloudLearnerBeyondSeed": None,
        },
        "teachingCycle": {
            "lessonsCreated": 0,
            "lessonsVisible": 0,
            "quizzesCreated": 0,
            "quizzesStarted": 0,
            "learnerSessionsOnAssigned": 0,
            "assignedShareOfLearnerVisits": None,
        },
        "learnersOperate": {
            "learnerSessions": 0,
            "learnerMinutes": 0,
            "coachSessions": 2,
            "coachMinutes": 10,
            "adminSessions": 2,
            "adminMinutes": 5,
            "guestVisits": 0,
            "guestMinutes": 0,
            "learnerShareOfMinutes": 0,
        },
        "nextcloud": {
            "worksheetShares": 0,
            "editShares": 0,
            "fileDropLinks": 5,
            "fileDropUploads": 0,
            "schoolFilesShares": 0,
            "officeOpens": 0,
            "officeOpensTeacherLearner": 0,
            "officeOpensAdmin": 0,
            "officeDistinctDocuments": 0,
            "officeRead": 0,
            "officeEdit": 0,
            "officeEstimatedMinutes": None,
        },
        "wikipedia": {"pageViewsOwn": 0, "sessionsOwn": 0, "distinctArticlesOwn": 0},
    }


def green_scorecard():
    card = amber_scorecard()
    card["available"]["schoolDaysOn"] = 4
    card["available"]["schoolHoursOnMinutes"] = 900
    card["setup"]["classes"] = 2
    card["setup"]["learnersRegistered"] = 8
    card["setup"]["teachers"] = 1
    card["teachingCycle"]["lessonsVisible"] = 1
    card["teachingCycle"]["learnerSessionsOnAssigned"] = 4
    card["learnersOperate"]["learnerSessions"] = 10
    card["learnersOperate"]["coachSessions"] = 2
    card["learnersOperate"]["adminSessions"] = 1
    card["nextcloud"]["officeOpens"] = 2
    card["nextcloud"]["officeOpensTeacherLearner"] = 2
    card["nextcloud"]["officeOpensAdmin"] = 0
    card["wikipedia"]["pageViewsOwn"] = 12
    return card


def weekly(starts, scorecards):
    return [
        {"weekStart": start, "scorecard": card, "hasUsageData": True}
        for start, card in zip(starts, scorecards)
    ]


class ThresholdValidationTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(DEFAULTS["availableMinSchoolDays"], 3)
        self.assertEqual(DEFAULTS["teachingCycleMinItems"], 1)
        self.assertEqual(DEFAULTS["learnerSessionShareMin"], 0.5)
        self.assertEqual(DEFAULTS["nextcloudMinActions"], 1)
        self.assertEqual(DEFAULTS["wikipediaMinViews"], 10)
        self.assertEqual(DEFAULTS["helpAfterAmberWeeks"], 3)
        self.assertEqual(DEFAULTS["unusedAfterHelpWeeks"], 4)

    def test_partial_merge_and_reset_persist(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "usage.sqlite")
        conn = db.connect(path)
        payload = apply_put(conn, {"thresholds": {"wikipediaMinViews": 20}}, "admin")
        self.assertEqual(payload["thresholds"]["wikipediaMinViews"], 20)
        self.assertEqual(payload["thresholds"]["availableMinSchoolDays"], 3)
        self.assertEqual(payload["defaults"]["wikipediaMinViews"], 10)
        self.assertEqual(payload["updatedBy"], "admin")
        self.assertIsNotNone(payload["updatedAt"])
        conn.close()

        again = db.connect(path)
        self.assertEqual(effective(again)["wikipediaMinViews"], 20)
        payload = apply_put(again, {"thresholds": {"availableMinSchoolDays": 4}}, "pixel")
        self.assertEqual(payload["thresholds"]["wikipediaMinViews"], 20)
        self.assertEqual(payload["thresholds"]["availableMinSchoolDays"], 4)
        self.assertEqual(payload["updatedBy"], "pixel")
        payload = apply_put(again, {"reset": True}, "pixel")
        self.assertEqual(payload["thresholds"], DEFAULTS)
        self.assertIsNone(payload["updatedAt"])
        self.assertIsNone(payload["updatedBy"])
        again.close()

        third = db.connect(path)
        self.assertEqual(effective(third), DEFAULTS)
        self.assertEqual(settings_payload(third)["updatedBy"], None)
        third.close()

    def test_validation_errors(self):
        cases = [
            ({"thresholds": {"noSuchKey": 1}}, "noSuchKey"),
            ({"thresholds": {"availableMinSchoolDays": -1}}, "availableMinSchoolDays"),
            ({"thresholds": {"availableMinSchoolDays": 6}}, "availableMinSchoolDays"),
            ({"thresholds": {"learnerSessionShareMin": 1.2}}, "learnerSessionShareMin"),
            ({"thresholds": {"learnerSessionShareMin": True}}, "learnerSessionShareMin"),
            ({"thresholds": {"helpAfterAmberWeeks": 0}}, "helpAfterAmberWeeks"),
            ({"thresholds": {"wikipediaMinViews": 2.5}}, "wikipediaMinViews"),
            ({"reset": "yes"}, "reset"),
            ({}, "thresholds"),
        ]
        for body, field in cases:
            with self.subTest(body=body):
                with self.assertRaises(ValidationError) as raised:
                    apply_put(None, body, "admin")
                self.assertEqual(raised.exception.field, field)
                self.assertTrue(raised.exception.error)


class ToneTests(unittest.TestCase):
    def test_green_and_amber_and_grey(self):
        self.assertEqual(week_tone(green_scorecard()), GREEN)
        self.assertEqual(week_tone(amber_scorecard()), AMBER)
        self.assertEqual(week_tone(empty_scorecard()), GREY)

    def test_teaching_cycle_needs_assigned_sessions(self):
        card = green_scorecard()
        card["teachingCycle"]["learnerSessionsOnAssigned"] = 0
        self.assertEqual(line_tones(card)["teachingCycle"], AMBER)

    def test_learner_share_uses_sessions_not_minutes(self):
        card = green_scorecard()
        card["learnersOperate"]["learnerSessions"] = 1
        card["learnersOperate"]["coachSessions"] = 10
        card["learnersOperate"]["adminSessions"] = 10
        card["learnersOperate"]["learnerMinutes"] = 100
        card["learnersOperate"]["coachMinutes"] = 1
        card["learnersOperate"]["adminMinutes"] = 1
        self.assertEqual(line_tones(card)["learnersOperate"], AMBER)

    def test_nextcloud_ignores_file_drop_links(self):
        card = amber_scorecard()
        card["nextcloud"]["fileDropLinks"] = 9
        self.assertEqual(line_tones(card)["nextcloud"], AMBER)
        card["nextcloud"]["officeOpens"] = 1
        card["nextcloud"]["officeOpensTeacherLearner"] = 1
        self.assertEqual(line_tones(card)["nextcloud"], GREEN)

    def test_nextcloud_ignores_admin_office_opens(self):
        card = amber_scorecard()
        card["nextcloud"]["officeOpens"] = 8
        card["nextcloud"]["officeOpensAdmin"] = 8
        card["nextcloud"]["officeOpensTeacherLearner"] = 0
        self.assertEqual(line_tones(card)["nextcloud"], AMBER)
        card["nextcloud"]["officeOpensTeacherLearner"] = 1
        self.assertEqual(line_tones(card)["nextcloud"], GREEN)

    def test_setup_is_yes_no(self):
        card = empty_scorecard()
        self.assertEqual(line_tones(card)["setup"], GREY)
        card["setup"]["teachers"] = 1
        card["setup"]["learnersRegistered"] = 0
        self.assertEqual(line_tones(card)["setup"], AMBER)
        card["setup"]["learnersRegistered"] = 8
        self.assertEqual(line_tones(card)["setup"], GREEN)


class StreakTests(unittest.TestCase):
    STARTS = ["2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"]

    def test_grey_does_not_count_or_break_amber_streak(self):
        rows = weekly(
            self.STARTS,
            [amber_scorecard(), empty_scorecard(), amber_scorecard(), amber_scorecard()],
        )
        count, start = amber_streak(rows)
        self.assertEqual(count, 3)
        self.assertEqual(start, "2026-10-19")

    def test_green_resets_amber_streak(self):
        rows = weekly(
            self.STARTS,
            [amber_scorecard(), amber_scorecard(), green_scorecard(), amber_scorecard()],
        )
        count, start = amber_streak(rows)
        self.assertEqual(count, 1)
        self.assertEqual(start, "2026-11-09")

    def test_help_after_three_amber_weeks(self):
        rows = weekly(self.STARTS[:2], [amber_scorecard(), amber_scorecard()])
        self.assertIsNone(help_suggestions_for(
            {"hasUsageData": True}, KIT, rows[-1]["scorecard"],
            weekly=rows, week_start=rows[-1]["weekStart"],
        ))
        rows = weekly(self.STARTS[:3], [amber_scorecard()] * 3)
        sug = help_suggestions_for(
            {"hasUsageData": True}, KIT, rows[-1]["scorecard"],
            weekly=rows, week_start=rows[-1]["weekStart"],
        )
        self.assertIsNotNone(sug)
        self.assertIn("offer help", sug["message"])
        self.assertIn("3 consecutive school weeks", sug["message"])

    def test_help_not_repeated_after_event_in_streak(self):
        rows = weekly(self.STARTS[:3], [amber_scorecard()] * 3)
        sug = help_suggestions_for(
            {"hasUsageData": True}, KIT, rows[-1]["scorecard"],
            weekly=rows, week_start="2026-11-02",
            help_events=[{"offeredOn": "2026-11-04"}],
        )
        self.assertIsNone(sug)

    def test_unused_after_help_without_improvement(self):
        starts = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"]
        rows = weekly(starts, [amber_scorecard()] * 6)
        events = [{"offeredOn": "2026-10-14"}]
        self.assertEqual(unused_streak(rows, events), 4)
        status = help_status_for(
            {"hasUsageData": True}, KIT, rows[-1]["scorecard"],
            weekly=rows, help_events=events, week_start="2026-11-09",
        )
        self.assertTrue(status["unused"])
        self.assertIsNone(status["suggestion"])

    def test_improvement_resets_unused(self):
        starts = ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"]
        cards = [amber_scorecard() for _ in starts]
        better = amber_scorecard()
        better["wikipedia"]["pageViewsOwn"] = 4
        cards[-1] = better
        rows = weekly(starts, cards)
        self.assertEqual(unused_streak(rows, [{"offeredOn": "2026-10-14"}]), 0)

    def test_no_data_yet_still_offers_help(self):
        kit = dict(KIT)
        kit["last_pulled"] = None
        kit["monitoring_enabled"] = 1
        sug = help_suggestions_for({"hasUsageData": False}, kit, empty_scorecard())
        self.assertIsNotNone(sug)
        self.assertIn("no pulled usage data yet", sug["message"])

    def test_monitoring_off_skips_help(self):
        kit = dict(KIT)
        kit["monitoring_enabled"] = 0
        rows = weekly(self.STARTS[:3], [amber_scorecard()] * 3)
        status = help_status_for(
            {"hasUsageData": True}, kit, rows[-1]["scorecard"],
            weekly=rows, week_start=rows[-1]["weekStart"],
        )
        self.assertIsNone(status["suggestion"])
        self.assertFalse(status["unused"])

    def test_single_outside_hours_week_is_amber_but_not_help(self):
        scorecard = empty_scorecard()
        scorecard["available"]["schoolDaysOn"] = 0
        scorecard["available"]["schoolHoursOnMinutes"] = 0
        self.assertEqual(week_tone(scorecard), AMBER)
        sug = help_suggestions_for({"hasUsageData": True}, KIT, scorecard)
        self.assertIsNone(sug)


if __name__ == "__main__":
    unittest.main()
