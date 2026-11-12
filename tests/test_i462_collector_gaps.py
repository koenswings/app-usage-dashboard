"""idea#462 collector gaps: U-7 Set up, enrolment, distinct users, Nextcloud
appsOpened / documents created, and one own-copy set for census and sessions.

Contract fixtures are real hook output (tests/fixtures/hook-real/).
"""
import copy
import itertools
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import aggregate as agg
from src import db
from src import thresholds as th
from src.aggregate import kiwix_week, kolibri_week, nextcloud_week, school_census, scorecard_from_weeks
from src.api import handle
from src.pull import store_export
from src.thresholds import AMBER, GREEN, GREY, line_tones, nextcloud_actions, setup_status, week_tone

REAL = Path(__file__).resolve().parent / "fixtures" / "hook-real"
WEEK = "2026-11-09"


def real(name):
    return json.loads((REAL / name).read_text(encoding="utf-8"))


def as_row(payload, day=None, instance=None, demo=None, hook="ok"):
    payload = copy.deepcopy(payload)
    if day:
        payload["day"] = day
    if instance:
        payload["instance"] = instance
    if demo is not None:
        payload["demo"] = demo
    payload.setdefault("hookStatus", hook)
    payload.setdefault("listed", True)
    payload.setdefault("instance", "inst")
    return {
        "day": payload["day"], "instance": payload["instance"], "app": payload["app"],
        "hook_status": payload["hookStatus"], "payload": json.dumps(payload),
    }


def kolibri_day(classes=1, coach_beyond=1, enrolled=3, learners=4, day=WEEK, instance="kolibri-own",
                sessions=2, users=2, demo=False):
    """Real Kolibri hook shape (app-kolibri hooks/usage.sh) with chosen values."""
    p = real("kolibri-0.19.5-engine-day.json")
    p["setup"]["classes"] = classes
    p["setup"]["learnerEnrolled"] = enrolled
    p["setup"]["teacher"] = {"total": (coach_beyond or 0) + 2, "beyondSeed": coach_beyond}
    p["setup"]["learner"] = {"total": learners, "beyondSeed": learners}
    p["signins"]["learner"].update({"total": users, "beyondSeed": users, "sessions": sessions})
    return as_row(p, day=day, instance=instance, demo=demo)


def nextcloud_day(teacher_beyond=1, learner_beyond=1, day=WEEK, instance="nextcloud-own", extra=None):
    p = real("nextcloud-31-engine-day.json")
    p["setup"]["teacher"]["beyondSeed"] = teacher_beyond
    p["setup"]["learner"]["beyondSeed"] = learner_beyond
    if extra:
        p.update(extra)
    return as_row(p, day=day, instance=instance)


def card_for(kolibri_rows=(), nextcloud_rows=(), kiwix_rows=()):
    def weeks(fn, rows):
        grouped = agg.group_by_instance(list(rows))
        return [fn(items) for items in grouped.values()]
    return scorecard_from_weeks(
        weeks(kolibri_week, kolibri_rows), weeks(nextcloud_week, nextcloud_rows),
        weeks(kiwix_week, kiwix_rows), [], WEEK,
    )


class RulingConstantsTests(unittest.TestCase):
    def test_rulings_are_single_constants(self):
        self.assertTrue(th.SETUP_REQUIRES_BOTH_APPS)                 # ruling 1
        self.assertEqual(agg.CENSUS_ACROSS_COPIES, "max")             # ruling 2
        self.assertNotIn("documentsCreatedTeacherLearner", th.NEXTCLOUD_LINE5_KEYS)  # ruling 3
        self.assertEqual(dict(th.KOLIBRI_SETUP_CHECKS)["coach"], "coachesBeyondSeed")  # ruling 4
        self.assertFalse(th.NEXTCLOUD_LINE5_COUNTS_OFFICE_OPENS)     # ruling 5
        self.assertNotIn("officeOpensTeacherLearner", th.NEXTCLOUD_LINE5_KEYS)
        self.assertEqual(th.SETUP_RULE, "u7-2026-11-11")


class RealHookContractTests(unittest.TestCase):
    def test_kolibri_real_hook_names_fill_census_and_users(self):
        week = kolibri_week([as_row(real("kolibri-0.19.5-engine-day.json"))])
        setup = week["setup"]
        self.assertEqual(setup["learnersEnrolled"], 0)       # was always None in 1.1
        self.assertEqual(setup["learnersRegisteredDelta"], 0)
        self.assertEqual(setup["learnersRegistered"], 1)
        self.assertEqual(setup["teachers"], 1)
        self.assertEqual(setup["admins"], 1)
        self.assertEqual(setup["coachesBeyondSeed"], 0)
        self.assertEqual(setup["classes"], 0)
        self.assertEqual(week["signins"]["learner"]["users"], 1)  # was 0 in 1.1
        self.assertEqual(week["signins"]["learner"]["usersBeyondSeed"], 0)
        self.assertEqual(week["signins"]["learner"]["sessions"], 1)

    def test_kolibri_0155_stdout_parses_and_demo_is_not_own(self):
        p = real("kolibri-0.15.5-hook-stdout.json")
        p.update({"instance": "kolibri-demo", "hookStatus": "ok", "listed": True})
        week = kolibri_week([as_row(p)])
        self.assertTrue(week["demo"])
        self.assertEqual(week["setup"]["learnersRegistered"], 2)
        self.assertEqual(week["signins"]["learner"]["users"], 1)
        card = card_for(kolibri_rows=[as_row(p)])
        self.assertEqual(card["copies"]["kolibri"], [])
        self.assertEqual(card["setupStatus"]["kolibri"]["missing"], ["noOwnKolibri"])

    def test_nextcloud_real_hook_has_no_apps_or_documents_yet(self):
        week = nextcloud_week([as_row(real("nextcloud-31-engine-day.json"))])
        self.assertIsNone(week["appsOpened"])
        self.assertIsNone(week["documentsCreated"])
        self.assertIsNone(week["documentsCreatedByGroup"])
        card = card_for(nextcloud_rows=[as_row(real("nextcloud-31-engine-day.json"))])
        self.assertIsNone(card["nextcloud"]["appsOpened"])
        self.assertIsNone(card["nextcloud"]["documentsCreated"])
        self.assertIsNone(card["nextcloud"]["documentsCreatedTeacherLearner"])
        # editShares teacher 2 + fileDropUploads teacher 2 (real byGroup), admin excluded.
        self.assertEqual(nextcloud_actions(card), 4)
        self.assertEqual(card["setup"]["nextcloudTeacherBeyondSeed"], 0)
        self.assertEqual(card["copies"]["nextcloud"], ["nextcloud-5u9958ql3enz59vaasi"])

    def test_kiwix_real_hook_feeds_copies(self):
        card = card_for(kiwix_rows=[as_row(real("kiwix-3.8.2-engine-day.json"))])
        self.assertEqual(card["copies"]["kiwix"], ["kiwix-iogyoms7aan8cctj42p"])
        self.assertEqual(card["wikipedia"]["pageViewsOwn"], 1)

    def test_real_idea_proof_pair_is_amber_with_reasons(self):
        card = card_for([as_row(real("kolibri-0.19.5-engine-day.json"))],
                        [as_row(real("nextcloud-31-engine-day.json"))])
        status = card["setupStatus"]
        self.assertIs(status["complete"], False)
        self.assertEqual(status["kolibri"]["missing"], ["coach", "class", "enrolledLearner"])
        self.assertEqual(status["nextcloud"]["missing"], ["teacherBeyondSeed", "learnerBeyondSeed"])
        self.assertEqual(line_tones(card)["setup"], AMBER)


class SetupTruthTableTests(unittest.TestCase):
    VALUES = (1, 0, None)  # pass, fail, unknown

    @staticmethod
    def oracle_part(values):
        if any(v == 0 for v in values):
            return False
        if any(v is None for v in values):
            return None
        return True

    def test_full_single_copy_truth_table(self):
        names_k = [n for n, _ in th.KOLIBRI_SETUP_CHECKS]
        names_n = [n for n, _ in th.NEXTCLOUD_SETUP_CHECKS]
        count = 0
        for kv in itertools.product(self.VALUES, repeat=3):
            for nv in itertools.product(self.VALUES, repeat=2):
                k_inputs = dict(zip([key for _, key in th.KOLIBRI_SETUP_CHECKS], kv))
                n_inputs = dict(zip([key for _, key in th.NEXTCLOUD_SETUP_CHECKS], nv))
                status = setup_status([("k1", k_inputs)], [("n1", n_inputs)], True)
                kp, np_ = self.oracle_part(kv), self.oracle_part(nv)
                overall = False if False in (kp, np_) else (None if None in (kp, np_) else True)
                msg = (kv, nv, status)
                self.assertIs(status["kolibri"]["complete"], kp, msg)
                self.assertIs(status["nextcloud"]["complete"], np_, msg)
                self.assertIs(status["complete"], overall, msg)
                if kp is True:
                    self.assertEqual(status["kolibri"]["passingInstanceIds"], ["k1"])
                    self.assertEqual(status["kolibri"]["missing"], [])
                else:
                    self.assertEqual(status["kolibri"]["missing"], [n for n, v in zip(names_k, kv) if v == 0])
                    self.assertEqual(status["kolibri"]["unknown"], [n for n, v in zip(names_k, kv) if v is None])
                if np_ is not True:
                    self.assertEqual(status["nextcloud"]["missing"], [n for n, v in zip(names_n, nv) if v == 0])
                tone = {True: GREEN, False: AMBER, None: GREY}[overall]
                self.assertEqual(th.setup_tone({"setupStatus": status}), tone)
                count += 1
        self.assertEqual(count, 243)

    def test_missing_own_app_fails_that_part(self):
        ok_k = {"coachesBeyondSeed": 1, "classes": 1, "learnersEnrolled": 1}
        ok_n = {"teacherBeyondSeed": 1, "learnerBeyondSeed": 1}
        s = setup_status([("k1", ok_k)], [], True)
        self.assertIs(s["complete"], False)
        self.assertEqual(s["nextcloud"]["missing"], ["noOwnNextcloud"])
        s = setup_status([], [("n1", ok_n)], True)
        self.assertIs(s["complete"], False)
        self.assertEqual(s["kolibri"]["missing"], ["noOwnKolibri"])
        # Missing app + unknown other part: still false (a failure beats unknown).
        s = setup_status([("k1", None)], [], True)
        self.assertIs(s["complete"], False)

    def test_no_data_at_all_is_grey(self):
        s = setup_status([], [], False)
        self.assertIsNone(s["complete"])
        self.assertIsNone(s["kolibri"])
        self.assertIsNone(s["nextcloud"])

    def test_copy_without_ok_day_is_unknown_never_passing(self):
        ok_n = {"teacherBeyondSeed": 1, "learnerBeyondSeed": 1}
        s = setup_status([("k1", None)], [("n1", ok_n)], True)
        self.assertIsNone(s["kolibri"]["complete"])
        self.assertEqual(s["kolibri"]["unknown"], ["coach", "class", "enrolledLearner"])
        self.assertIsNone(s["complete"])

    def test_any_one_copy_must_pass_on_its_own(self):
        ok_n = {"teacherBeyondSeed": 1, "learnerBeyondSeed": 1}
        a = {"coachesBeyondSeed": 1, "classes": 0, "learnersEnrolled": 5}
        b = {"coachesBeyondSeed": 0, "classes": 2, "learnersEnrolled": 5}
        s = setup_status([("a", a), ("b", b)], [("n", ok_n)], True)
        self.assertIs(s["kolibri"]["complete"], False)  # no mixing a's coach with b's class
        self.assertEqual(s["kolibri"]["missing"], ["coach", "class"])
        c = {"coachesBeyondSeed": 1, "classes": 1, "learnersEnrolled": 1}
        s = setup_status([("a", a), ("c", c)], [("n", ok_n)], True)
        self.assertIs(s["complete"], True)
        self.assertEqual(s["kolibri"]["passingInstanceIds"], ["c"])
        # one failing copy and one unknown copy: unknown (the unknown copy might pass)
        s = setup_status([("a", a), ("u", None)], [("n", ok_n)], True)
        self.assertIsNone(s["kolibri"]["complete"])

    def test_requires_both_apps_switch(self):
        ok_k = {"coachesBeyondSeed": 1, "classes": 1, "learnersEnrolled": 1}
        old = th.SETUP_REQUIRES_BOTH_APPS
        try:
            th.SETUP_REQUIRES_BOTH_APPS = False
            s = setup_status([("k1", ok_k)], [], True)
            self.assertIs(s["complete"], True)
            self.assertIsNone(s["nextcloud"])
        finally:
            th.SETUP_REQUIRES_BOTH_APPS = old


class Idea03ZeroClassesTests(unittest.TestCase):
    def test_zero_classes_goes_amber_even_with_coach_and_learners(self):
        card = card_for([kolibri_day(classes=0, coach_beyond=1, enrolled=0, learners=6)],
                        [nextcloud_day(1, 1)])
        self.assertEqual(card["setup"]["classes"], 0)
        self.assertEqual(card["setupStatus"]["kolibri"]["missing"], ["class", "enrolledLearner"])
        self.assertIs(card["setupStatus"]["complete"], False)
        self.assertEqual(line_tones(card)["setup"], AMBER)
        self.assertEqual(week_tone(card), AMBER)

    def test_old_rule_would_have_been_green(self):
        # learnersRegistered>0 && teachers>0 held here; U-7 does not.
        card = card_for([kolibri_day(classes=0, coach_beyond=1, enrolled=0)], [nextcloud_day(1, 1)])
        self.assertGreater(card["setup"]["learnersRegistered"], 0)
        self.assertGreater(card["setup"]["teachers"], 0)
        self.assertEqual(line_tones(card)["setup"], AMBER)

    def test_fully_set_up_school_is_green(self):
        card = card_for([kolibri_day()], [nextcloud_day(1, 1)])
        self.assertIs(card["setupStatus"]["complete"], True)
        self.assertEqual(line_tones(card)["setup"], GREEN)

    def test_seed_only_coaches_do_not_count(self):
        card = card_for([kolibri_day(coach_beyond=0)], [nextcloud_day(1, 1)])
        self.assertEqual(card["setup"]["teachers"], 2)  # teacher1/teacher2 seeds
        self.assertEqual(card["setupStatus"]["kolibri"]["missing"], ["coach"])

    def test_nextcloud_needs_teacher_and_learner_beyond_seed(self):
        card = card_for([kolibri_day()], [nextcloud_day(1, 0)])
        self.assertEqual(card["setupStatus"]["nextcloud"]["missing"], ["learnerBeyondSeed"])
        self.assertEqual(line_tones(card)["setup"], AMBER)

    def test_help_suggestion_driven_by_setup_status(self):
        kit = {"engine": "idea03", "school": "idea03 (proof)", "deployment_id": "dep-idea03",
               "monitoring_enabled": 1, "last_pulled": "2026-11-12T08:00:00+01:00"}
        amber = card_for([kolibri_day(classes=0)], [nextcloud_day(1, 1)])
        # Every other line green, so Set up alone drives the streak.
        green_lines = {"available": GREEN, "teachingCycle": GREEN, "learnersOperate": GREEN,
                       "nextcloud": GREEN, "wikipedia": GREEN}
        orig = th.line_tones
        try:
            th.line_tones = lambda sc, t=None: dict(green_lines, setup=th.setup_tone(sc))
            weekly = [{"weekStart": w, "scorecard": amber, "hasUsageData": True}
                      for w in ("2026-10-26", "2026-11-02", "2026-11-09")]
            status = agg.help_status_for({"hasUsageData": True}, kit, amber, weekly=weekly, week_start=WEEK)
            self.assertIsNotNone(status["suggestion"])
            ok = card_for([kolibri_day()], [nextcloud_day(1, 1)])
            weekly[-1] = {"weekStart": WEEK, "scorecard": ok, "hasUsageData": True}
            status = agg.help_status_for({"hasUsageData": True}, kit, ok, weekly=weekly, week_start=WEEK)
            self.assertIsNone(status["suggestion"])
        finally:
            th.line_tones = orig


class SameCopiesTests(unittest.TestCase):
    def test_census_is_max_and_sessions_are_summed_over_the_same_copies(self):
        a = kolibri_day(classes=3, coach_beyond=1, enrolled=20, learners=25, instance="kolibri-b", sessions=5)
        b = kolibri_day(classes=3, coach_beyond=1, enrolled=18, learners=25, instance="kolibri-a", sessions=7)
        demo = kolibri_day(classes=9, coach_beyond=9, enrolled=99, learners=99, instance="kolibri-demo",
                           sessions=50, demo=True)
        card = card_for([a, b, demo], [nextcloud_day(1, 1)])
        self.assertEqual(card["copies"]["kolibri"], ["kolibri-a", "kolibri-b"])  # sorted, demo excluded
        self.assertEqual(card["setup"]["classes"], 3)            # max, not 6 (clones)
        self.assertEqual(card["setup"]["learnersEnrolled"], 20)  # max
        self.assertEqual(card["setup"]["learnersRegistered"], 25)
        self.assertEqual(card["learnersOperate"]["learnerSessions"], 12)  # activity summed
        self.assertEqual(card["setupStatus"]["kolibri"]["passingInstanceIds"], ["kolibri-a", "kolibri-b"])

    def test_school_census_matches_scorecard_setup(self):
        rows = [kolibri_day(classes=1, instance="kolibri-z"), kolibri_day(classes=4, instance="kolibri-y")]
        weeks = [kolibri_week(items) for items in agg.group_by_instance(rows).values()]
        census = school_census(weeks)
        card = scorecard_from_weeks(weeks, [], [], [], WEEK)
        for key in ("classes", "learnersRegistered", "learnersEnrolled", "teachers", "admins"):
            self.assertEqual(census[key], card["setup"][key], key)
        self.assertEqual(census["coachesBeyondSeed"], card["setup"]["kolibriCoachBeyondSeed"])

    def test_copy_order_does_not_change_the_census(self):
        rows = [kolibri_day(classes=1, instance="kolibri-z"), kolibri_day(classes=4, instance="kolibri-y")]
        one = card_for(rows)
        two = card_for(list(reversed(rows)))
        self.assertEqual(one["setup"], two["setup"])

    def test_nextcloud_beyond_seed_is_max_across_copies(self):
        card = card_for([kolibri_day()], [nextcloud_day(0, 3, instance="nc-a"), nextcloud_day(2, 0, instance="nc-b")])
        self.assertEqual(card["setup"]["nextcloudTeacherBeyondSeed"], 2)
        self.assertEqual(card["setup"]["nextcloudLearnerBeyondSeed"], 3)
        # But no single copy has both: not set up.
        self.assertIs(card["setupStatus"]["nextcloud"]["complete"], False)

    def test_failed_copy_is_listed_as_unknown_not_dropped(self):
        stub = as_row({"schema": "idea-usage-day/1", "day": WEEK, "app": "kolibri",
                       "instance": "kolibri-timeout", "hookStatus": "timeout"}, hook="timeout")
        card = card_for([stub], [nextcloud_day(1, 1)])
        self.assertEqual(card["copies"]["kolibri"], [])
        self.assertIsNone(card["setup"]["classes"])
        self.assertIsNone(card["setupStatus"]["kolibri"]["complete"])
        self.assertIsNone(card["setupStatus"]["complete"])


class DistinctUsersTests(unittest.TestCase):
    def test_weekly_users_is_max_of_daily_distinct(self):
        rows = [kolibri_day(day="2026-11-09", users=3, sessions=4),
                kolibri_day(day="2026-11-10", users=5, sessions=6),
                kolibri_day(day="2026-11-11", users=2, sessions=2)]
        week = kolibri_week(rows)
        self.assertEqual(week["signins"]["learner"]["users"], 5)
        self.assertEqual(week["signins"]["learner"]["usersBeyondSeed"], 5)
        self.assertEqual(week["signins"]["learner"]["sessions"], 12)


class NextcloudFutureHookTests(unittest.TestCase):
    def test_apps_opened_measured_empty_is_empty_object(self):
        week = nextcloud_week([nextcloud_day(extra={"appsOpened": {}})])
        self.assertEqual(week["appsOpened"], {})

    def test_apps_opened_and_documents_pass_through_and_sum(self):
        docs = {"created": 3, "byGroup": {"admin": 1, "teacher": 1, "learner": 1}}
        rows = [nextcloud_day(day="2026-11-09", extra={"appsOpened": {"files": 4}, "documents": docs}),
                nextcloud_day(day="2026-11-10", extra={"appsOpened": {"files": 1, "richdocuments": 2},
                                                        "documents": docs})]
        week = nextcloud_week(rows)
        self.assertEqual(week["appsOpened"], {"files": 5, "richdocuments": 2})
        self.assertEqual(week["documentsCreated"], 6)
        self.assertEqual(week["documentsCreatedByGroup"], {"admin": 2, "teacher": 2, "learner": 2})
        card = card_for([kolibri_day()], rows)
        self.assertEqual(card["nextcloud"]["documentsCreated"], 6)
        self.assertEqual(card["nextcloud"]["documentsCreatedTeacherLearner"], 4)
        self.assertEqual(card["nextcloud"]["documentsCreatedAdmin"], 2)
        self.assertEqual(card["nextcloud"]["appsOpened"], {"files": 5, "richdocuments": 2})

    def test_documents_without_split_have_null_split(self):
        rows = [nextcloud_day(extra={"documents": {"created": 2}})]
        card = card_for([kolibri_day()], rows)
        self.assertEqual(card["nextcloud"]["documentsCreated"], 2)
        self.assertIsNone(card["nextcloud"]["documentsCreatedTeacherLearner"])
        self.assertIsNone(card["nextcloud"]["documentsCreatedAdmin"])

    def test_documents_created_do_not_count_for_line5(self):
        p = nextcloud_day(extra={"documents": {"created": 9, "byGroup": {"admin": 0, "teacher": 9, "learner": 0}}})
        payload = json.loads(p["payload"])
        for key in payload["workflows"]["byGroup"]:
            payload["workflows"]["byGroup"][key] = {"admin": 0, "teacher": 0, "learner": 0}
        p["payload"] = json.dumps(payload)
        card = card_for([kolibri_day()], [p])
        self.assertEqual(nextcloud_actions(card), 0)
        self.assertEqual(line_tones(card)["nextcloud"], AMBER)


class OldDayFileTests(unittest.TestCase):
    SKETCH = {
        "schema": "idea-usage-day/1", "day": WEEK, "app": "kolibri", "instance": "kolibri-old",
        "setup": {"classes": 2, "classesDelta": 0, "learnersRegistered": 8, "learnersRegisteredDelta": 1,
                  "learnersEnrolled": 6, "teachers": 1, "teachersDelta": 0, "admins": 1},
        "signins": {"learner": {"users": 4, "sessions": 4, "minutes": 10},
                    "coach": {"users": 1, "sessions": 1, "minutes": 5},
                    "admin": {"users": 0, "sessions": 0, "minutes": 0}},
        "guest": {"visits": 0, "seconds": 0},
        "teaching": {"lessonsCreated": 0, "lessonsVisible": 0, "quizzesCreated": 0,
                     "quizzesStarted": 0, "quizzesEnded": 0},
        "content": [],
    }

    def test_sketch_shape_still_parses(self):
        week = kolibri_week([as_row(self.SKETCH)])
        self.assertEqual(week["setup"]["learnersEnrolled"], 6)
        self.assertEqual(week["setup"]["learnersRegistered"], 8)
        self.assertEqual(week["setup"]["learnersRegisteredDelta"], 1)
        self.assertEqual(week["setup"]["teachers"], 1)
        self.assertIsNone(week["setup"]["coachesBeyondSeed"])  # flat teachers: no seed info
        self.assertEqual(week["signins"]["learner"]["users"], 4)
        self.assertIsNone(week["signins"]["learner"]["usersBeyondSeed"])

    def test_old_kolibri_without_beyond_seed_is_unknown_not_passing(self):
        card = card_for([as_row(self.SKETCH)], [nextcloud_day(1, 1)])
        self.assertEqual(card["setupStatus"]["kolibri"]["unknown"], ["coach"])
        self.assertIsNone(card["setupStatus"]["complete"])
        self.assertEqual(line_tones(card)["setup"], GREY)

    def test_old_nextcloud_legacy_setup_parses(self):
        p = {"schema": "idea-usage-day/1", "day": WEEK, "app": "nextcloud", "instance": "nc-old",
             "setup": {"admin": 1, "teachers": 3, "learners": 4, "otherGroups": {}},
             "logins": {"admin": {"users": 1}, "teacher": {"users": 2}, "learner": {"users": 1}}}
        week = nextcloud_week([as_row(p)])
        self.assertEqual(week["setup"]["teacher"], {"total": 3, "beyondSeed": None})
        self.assertIsNone(week["appsOpened"])
        card = card_for([kolibri_day()], [as_row(p)])
        self.assertEqual(card["setupStatus"]["nextcloud"]["unknown"], ["teacherBeyondSeed", "learnerBeyondSeed"])
        self.assertIsNone(card["setupStatus"]["complete"])


class ApiShapeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmp, "usage.sqlite"))
        registry = os.path.join(self.tmp, "registry.json")
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump({"kits": [{"engine": "idea03", "tailscaleName": "idea03", "school": "idea03 (proof)",
                                 "deploymentId": "dep-idea03", "timezone": "Europe/Brussels", "note": ""}]}, fh)
        db.load_registry(self.conn, registry)
        days = []
        for row in (kolibri_day(classes=0, instance="kolibri-b"), kolibri_day(classes=0, instance="kolibri-a"),
                    nextcloud_day(1, 1)):
            payload = json.loads(row["payload"])
            payload["engine"] = "idea03"
            days.append({"type": "day", "day": WEEK, "instance": payload["instance"], "payload": payload})
        store_export(self.conn, "idea03", {"presence": [], "days": days, "samples": [],
                                           "end": {"type": "end", "counts": {"day": 3}, "errors": 0}},
                     "2026-11-12T08:00:00+01:00", "dep-idea03")
        self.conn.commit()
        os.environ["IDEA_USAGE_KOEN_PASSWORD"] = "koen911!"
        os.environ["IDEA_USAGE_PBKDF2_ITERATIONS"] = "1000"
        os.environ["IDEA_USAGE_OPERATORS_FILE"] = os.path.join(self.tmp, "operators.json")
        os.environ["IDEA_USAGE_SESSION_SECRET"] = "test-secret"

    def tearDown(self):
        self.conn.close()

    def get(self, path):
        status, body, _ = handle(self.conn, "GET", path, None, "koen", False)
        self.assertEqual(status, 200, body)
        return body

    def test_overview_school_week_and_app_endpoints(self):
        overview = self.get("/api/v1/weeks/%s/overview" % WEEK)
        sc = overview["cards"][0]["scorecard"]
        self.assertIs(sc["setupStatus"]["complete"], False)
        self.assertEqual(sc["setupStatus"]["kolibri"]["missing"], ["class"])
        self.assertEqual(sc["copies"]["kolibri"], ["kolibri-a", "kolibri-b"])
        school = self.get("/api/v1/weeks/%s/schools/dep-idea03" % WEEK)
        self.assertEqual(school["scorecard"]["setupStatus"], sc["setupStatus"])
        for key in ("classes", "learnersRegistered", "learnersEnrolled", "teachers", "admins"):
            self.assertEqual(school["census"][key], school["scorecard"]["setup"][key], key)
        self.assertEqual(school["census"]["learnersEnrolled"], 3)
        kol = self.get("/api/v1/weeks/%s/schools/dep-idea03/kolibri" % WEEK)
        self.assertEqual(kol["instances"][0]["signins"]["learner"]["users"], 2)
        self.assertIn("usersBeyondSeed", kol["instances"][0]["signins"]["coach"])
        nc = self.get("/api/v1/weeks/%s/schools/dep-idea03/nextcloud" % WEEK)
        inst = nc["instances"][0]
        self.assertIsNone(inst["appsOpened"])
        self.assertIsNone(inst["documentsCreated"])
        self.assertIsNone(inst["documentsCreatedByGroup"])


if __name__ == "__main__":
    unittest.main()
