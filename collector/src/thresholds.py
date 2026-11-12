"""U-7 scorecard thresholds: defaults, SQLite persistence, and week tones.

Stored in the existing ``meta`` table of ``usage.sqlite`` (the App ``./data``
bind mount). Operator-editable via ``GET``/``PUT /api/v1/settings/thresholds``.
"""
from __future__ import annotations

import json
from typing import Any

from . import db

KEYS = (
    "availableMinSchoolDays",
    "teachingCycleMinItems",
    "learnerSessionShareMin",
    "nextcloudMinActions",
    "wikipediaMinViews",
    "helpAfterAmberWeeks",
    "unusedAfterHelpWeeks",
)

DEFAULTS: dict[str, Any] = {
    "availableMinSchoolDays": 3,
    "teachingCycleMinItems": 1,
    "learnerSessionShareMin": 0.5,
    "nextcloudMinActions": 1,
    "wikipediaMinViews": 10,
    "helpAfterAmberWeeks": 3,
    "unusedAfterHelpWeeks": 4,
}

GREEN = "green"
AMBER = "amber"
GREY = "grey"

_META_VALUE = "thresholds"
_META_UPDATED_AT = "thresholds_updated_at"
_META_UPDATED_BY = "thresholds_updated_by"

_INT_SPECS = {
    "availableMinSchoolDays": (0, 5),
    "teachingCycleMinItems": (0, None),
    "nextcloudMinActions": (0, None),
    "wikipediaMinViews": (0, None),
    # 0 would make ``streak >= 0`` true for a green week, so these start at 1.
    "helpAfterAmberWeeks": (1, None),
    "unusedAfterHelpWeeks": (1, None),
}


class ValidationError(Exception):
    def __init__(self, error: str, field: str):
        super().__init__(error)
        self.error = error
        self.field = field


def _meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else row["value"]


def _set_meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))


def _clear_meta(conn, key: str) -> None:
    conn.execute("DELETE FROM meta WHERE key = ?", (key,))


def defaults() -> dict[str, Any]:
    return dict(DEFAULTS)


def effective(conn=None) -> dict[str, Any]:
    values = defaults()
    if conn is None:
        return values
    raw = _meta(conn, _META_VALUE)
    if not raw:
        return values
    try:
        stored = json.loads(raw)
    except json.JSONDecodeError:
        return values
    if not isinstance(stored, dict):
        return values
    for key in KEYS:
        if key in stored:
            values[key] = stored[key]
    return values


def load_audit(conn) -> tuple[str | None, str | None]:
    updated_at = _meta(conn, _META_UPDATED_AT) or None
    updated_by = _meta(conn, _META_UPDATED_BY) or None
    return updated_at, updated_by


def settings_payload(conn=None) -> dict[str, Any]:
    if conn is None:
        return {
            "thresholds": defaults(),
            "defaults": defaults(),
            "updatedAt": None,
            "updatedBy": None,
        }
    updated_at, updated_by = load_audit(conn)
    return {
        "thresholds": effective(conn),
        "defaults": defaults(),
        "updatedAt": updated_at,
        "updatedBy": updated_by,
    }


def _as_int(value: Any, field: str, minimum: int, maximum: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("must be an integer", field)
    if isinstance(value, float):
        if not value.is_integer():
            raise ValidationError("must be an integer", field)
        value = int(value)
    if value < minimum:
        raise ValidationError("must be an integer >= %s" % minimum, field)
    if maximum is not None and value > maximum:
        raise ValidationError("must be an integer <= %s" % maximum, field)
    return int(value)


def _as_share(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("must be a number between 0 and 1", field)
    number = float(value)
    if number < 0 or number > 1:
        raise ValidationError("must be a number between 0 and 1", field)
    return number


def validate_partial(partial: Any) -> dict[str, Any]:
    if not isinstance(partial, dict):
        raise ValidationError("thresholds must be an object", "thresholds")
    out: dict[str, Any] = {}
    for key, value in partial.items():
        if key not in DEFAULTS:
            raise ValidationError("unknown threshold", key)
        if key == "learnerSessionShareMin":
            out[key] = _as_share(value, key)
        else:
            minimum, maximum = _INT_SPECS[key]
            out[key] = _as_int(value, key, minimum, maximum)
    return out


def save(conn, values: dict[str, Any], user: str | None) -> None:
    _set_meta(conn, _META_VALUE, json.dumps(values, separators=(",", ":")))
    _set_meta(conn, _META_UPDATED_AT, db.now_rfc3339())
    _set_meta(conn, _META_UPDATED_BY, user or "")
    conn.commit()


def reset(conn) -> None:
    _clear_meta(conn, _META_VALUE)
    _clear_meta(conn, _META_UPDATED_AT)
    _clear_meta(conn, _META_UPDATED_BY)
    conn.commit()


def apply_put(conn, body: Any, user: str | None) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ValidationError("request body must be an object", "thresholds")
    if body.get("reset") is True:
        reset(conn)
        return settings_payload(conn)
    if "reset" in body and body["reset"] is not False:
        raise ValidationError("reset must be true", "reset")
    if "thresholds" not in body:
        raise ValidationError("expected thresholds or reset", "thresholds")
    validated = validate_partial(body.get("thresholds"))
    if not validated:
        return settings_payload(conn)
    merged = effective(conn)
    merged.update(validated)
    save(conn, merged, user)
    return settings_payload(conn)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def teaching_items(scorecard: dict[str, Any]) -> int | None:
    teaching = scorecard.get("teachingCycle") or {}
    visible = _int_or_none(teaching.get("lessonsVisible"))
    started = _int_or_none(teaching.get("quizzesStarted"))
    created_lessons = _int_or_none(teaching.get("lessonsCreated"))
    created_quizzes = _int_or_none(teaching.get("quizzesCreated"))
    assigned = _int_or_none(teaching.get("learnerSessionsOnAssigned"))
    if all(v is None for v in (visible, started, created_lessons, created_quizzes, assigned)):
        return None
    return int(visible or 0) + int(started or 0)


def learner_session_share(scorecard: dict[str, Any]) -> float | None:
    learners = scorecard.get("learnersOperate") or {}
    learner = _int_or_none(learners.get("learnerSessions"))
    coach = _int_or_none(learners.get("coachSessions"))
    admin = _int_or_none(learners.get("adminSessions"))
    if learner is None and coach is None and admin is None:
        return None
    total = int(learner or 0) + int(coach or 0) + int(admin or 0)
    if total <= 0:
        return 0.0
    return int(learner or 0) / total


# U-7 line 5 (Nextcloud workflows), idea#462 ruling 5 (Steve, 2026-11-12):
# judged on shares, co-edits and File drop uploads by a teacher or learner.
# Office opens join only once the IDEA app-open counter ships in app-nextcloud
# (flip NEXTCLOUD_LINE5_COUNTS_OFFICE_OPENS then). Ruling 3: documents created
# are display only and never count here.
NEXTCLOUD_LINE5_COUNTS_OFFICE_OPENS = False
NEXTCLOUD_LINE5_KEYS = (
    "worksheetSharesTeacherLearner",
    "editSharesTeacherLearner",
    "schoolFilesSharesTeacherLearner",
    "fileDropUploadsTeacherLearner",
) + (("officeOpensTeacherLearner",) if NEXTCLOUD_LINE5_COUNTS_OFFICE_OPENS else ())


def nextcloud_actions(scorecard: dict[str, Any]) -> int | None:
    nc = scorecard.get("nextcloud") or {}
    # U-7 line 5: actions by a teacher or learner. Admin actions do not count.
    # A null split (old day files with no byGroup) contributes 0.
    parts = [nc.get(key) for key in NEXTCLOUD_LINE5_KEYS]
    if all(v is None for v in parts):
        return None
    return sum(int(v or 0) for v in parts)


def week_metrics(scorecard: dict[str, Any]) -> dict[str, float | int | None]:
    available = scorecard.get("available") or {}
    teaching = scorecard.get("teachingCycle") or {}
    wiki = scorecard.get("wikipedia") or {}
    return {
        "schoolDaysOn": _int_or_none(available.get("schoolDaysOn")),
        "teachingItems": teaching_items(scorecard),
        "assignedSessions": _int_or_none(teaching.get("learnerSessionsOnAssigned")),
        "learnerSessionShare": learner_session_share(scorecard),
        "nextcloudActions": nextcloud_actions(scorecard),
        "wikipediaViews": _int_or_none(wiki.get("pageViewsOwn")),
    }


def improved(current: dict[str, Any], baseline: dict[str, Any]) -> bool:
    now = week_metrics(current)
    before = week_metrics(baseline)
    for key, value in now.items():
        if value is None:
            continue
        previous = before.get(key)
        if previous is None:
            if value > 0:
                return True
        elif value > previous:
            return True
    return False


# --- U-7 Set up (idea#462). Rulings (Steve, 2026-11-12) are single constants. ---

SETUP_RULE = "u7-2026-11-11"

# Ruling 1: Set up is yes only when BOTH the Kolibri and the Nextcloud part
# pass. A school with no own copy of one app fails that part with the reason
# "noOwnKolibri" / "noOwnNextcloud". Set False to let a missing app not block.
SETUP_REQUIRES_BOTH_APPS = True

# Per-copy conditions. Ruling 4: a Kolibri coach means a coach BEYOND the seed
# accounts (``coachesBeyondSeed``), the same seed exclusion as Nextcloud.
KOLIBRI_SETUP_CHECKS = (
    ("coach", "coachesBeyondSeed"),
    ("class", "classes"),
    ("enrolledLearner", "learnersEnrolled"),
)
NEXTCLOUD_SETUP_CHECKS = (
    ("teacherBeyondSeed", "teacherBeyondSeed"),
    ("learnerBeyondSeed", "learnerBeyondSeed"),
)

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"


def _copy_verdict(inputs: dict[str, Any] | None, checks) -> tuple[str, list[str], list[str]]:
    """(verdict, failing parts, unknown parts) for one own copy.

    A copy with no ok day this week (``inputs`` None) is unknown on every part.
    A known failing condition makes the copy fail even if other parts are
    unknown, because it cannot pass whatever the unknown values are.
    """
    if inputs is None:
        return UNKNOWN, [], [name for name, _ in checks]
    failing, unknown = [], []
    for name, key in checks:
        value = _int_or_none(inputs.get(key))
        if value is None:
            unknown.append(name)
        elif value < 1:
            failing.append(name)
    if failing:
        return FAIL, failing, unknown
    if unknown:
        return UNKNOWN, [], unknown
    return PASS, [], []


def _ordered(names: set[str], checks) -> list[str]:
    return [name for name, _ in checks if name in names]


def app_setup_status(copies: list[tuple[str, dict[str, Any] | None]], checks, absent_reason: str) -> dict[str, Any] | None:
    """One app's part of U-7 Set up.

    ``copies`` lists the school's own (non-demo) copies of the app seen this
    week as ``(instanceId, inputs)``; ``inputs`` is None when the copy had no
    ok day. The part passes when ANY one copy passes on its own (a coach on
    copy A and a class on copy B do not combine). Otherwise it is unknown if
    any copy is unknown, else it fails.
    """
    if not copies:
        if not SETUP_REQUIRES_BOTH_APPS:
            return None
        return {"complete": False, "missing": [absent_reason], "unknown": [], "passingInstanceIds": []}
    passing: list[str] = []
    failing: set[str] = set()
    unknown: set[str] = set()
    any_unknown = False
    for instance_id, inputs in copies:
        verdict, fails, unknowns = _copy_verdict(inputs, checks)
        if verdict == PASS:
            passing.append(instance_id)
        elif verdict == UNKNOWN:
            any_unknown = True
        failing.update(fails)
        unknown.update(unknowns)
    if passing:
        return {"complete": True, "missing": [], "unknown": [], "passingInstanceIds": passing}
    return {
        "complete": None if any_unknown else False,
        "missing": _ordered(failing, checks),
        "unknown": _ordered(unknown, checks),
        "passingInstanceIds": [],
    }


def empty_setup_status() -> dict[str, Any]:
    return {"complete": None, "kolibri": None, "nextcloud": None, "rule": SETUP_RULE}


def setup_status(
    kolibri_copies: list[tuple[str, dict[str, Any] | None]],
    nextcloud_copies: list[tuple[str, dict[str, Any] | None]],
    has_data: bool,
) -> dict[str, Any]:
    """``scorecard.setupStatus``: the U-7 Set up verdict the UI shows.

    Truth table (parts are true / false / null):
      - no ok day-file from any app this week -> complete null, parts null;
      - any present part false               -> complete false (amber);
      - else any part null (unknown)         -> complete null (grey);
      - else (every part true)               -> complete true (green).
    An unknown part never counts as passing.
    """
    if not has_data:
        return empty_setup_status()
    kolibri = app_setup_status(kolibri_copies, KOLIBRI_SETUP_CHECKS, "noOwnKolibri")
    nextcloud = app_setup_status(nextcloud_copies, NEXTCLOUD_SETUP_CHECKS, "noOwnNextcloud")
    parts = [p["complete"] for p in (kolibri, nextcloud) if p is not None]
    if not parts:
        complete = None
    elif any(v is False for v in parts):
        complete = False
    elif any(v is None for v in parts):
        complete = None
    else:
        complete = True
    return {"complete": complete, "kolibri": kolibri, "nextcloud": nextcloud, "rule": SETUP_RULE}


def setup_tone(scorecard: dict[str, Any]) -> str:
    """Server tone for the Set up line, driven only by ``scorecard.setupStatus``."""
    status = scorecard.get("setupStatus") or {}
    complete = status.get("complete")
    if complete is True:
        return GREEN
    if complete is False:
        return AMBER
    return GREY


def line_tones(scorecard: dict[str, Any], thresholds: dict[str, Any] | None = None) -> dict[str, str]:
    thresholds = thresholds or DEFAULTS
    available = scorecard.get("available") or {}
    teaching = scorecard.get("teachingCycle") or {}
    wiki = scorecard.get("wikipedia") or {}

    days = _int_or_none(available.get("schoolDaysOn"))
    school_minutes = _int_or_none(available.get("schoolHoursOnMinutes"))
    if days is None and school_minutes is None:
        available_tone = GREY
    else:
        available_tone = GREEN if int(days or 0) >= thresholds["availableMinSchoolDays"] else AMBER

    setup_line = setup_tone(scorecard)

    items = teaching_items(scorecard)
    assigned = _int_or_none(teaching.get("learnerSessionsOnAssigned"))
    if items is None:
        teaching_tone = GREY
    else:
        teaching_tone = (
            GREEN
            if items >= thresholds["teachingCycleMinItems"] and int(assigned or 0) >= 1
            else AMBER
        )

    share = learner_session_share(scorecard)
    learners_tone = GREY if share is None else (
        GREEN if share >= thresholds["learnerSessionShareMin"] else AMBER
    )

    actions = nextcloud_actions(scorecard)
    nextcloud_tone = GREY if actions is None else (
        GREEN if actions >= thresholds["nextcloudMinActions"] else AMBER
    )

    views = _int_or_none(wiki.get("pageViewsOwn"))
    wikipedia_tone = GREY if views is None else (
        GREEN if views >= thresholds["wikipediaMinViews"] else AMBER
    )

    return {
        "available": available_tone,
        "setup": setup_line,
        "teachingCycle": teaching_tone,
        "learnersOperate": learners_tone,
        "nextcloud": nextcloud_tone,
        "wikipedia": wikipedia_tone,
    }


def week_tone(scorecard: dict[str, Any], thresholds: dict[str, Any] | None = None) -> str:
    """Overall week colour. Grey lines are ignored; grey never starts a streak."""
    tones = line_tones(scorecard, thresholds)
    valued = [tone for tone in tones.values() if tone != GREY]
    if not valued:
        return GREY
    if any(tone == AMBER for tone in valued):
        return AMBER
    return GREEN


def amber_streak(weekly: list[dict[str, Any]], thresholds: dict[str, Any] | None = None) -> tuple[int, str | None]:
    """Trailing consecutive amber weeks, skipping grey. Returns (count, oldest weekStart)."""
    streak = 0
    start = None
    for entry in reversed(weekly):
        tone = week_tone(entry["scorecard"], thresholds)
        if tone == GREY:
            continue
        if tone == GREEN:
            break
        streak += 1
        start = entry.get("weekStart")
    return streak, start


def unused_streak(
    weekly: list[dict[str, Any]],
    help_events: list[dict[str, Any]] | None,
    thresholds: dict[str, Any] | None = None,
) -> int:
    """Trailing amber-with-no-improvement weeks after the latest help event."""
    if not help_events:
        return 0
    offered = None
    for event in help_events:
        date = event.get("offeredOn") or event.get("offered_on")
        if date and (offered is None or date > offered):
            offered = date
    if not offered:
        return 0
    baseline = None
    after: list[dict[str, Any]] = []
    for entry in weekly:
        start = entry.get("weekStart")
        if not start:
            continue
        if start <= offered:
            baseline = entry
        elif start > offered:
            after.append(entry)
    if baseline is None and after:
        baseline = after[0]
    if baseline is None:
        return 0
    streak = 0
    for entry in after:
        tone = week_tone(entry["scorecard"], thresholds)
        if tone == GREY:
            continue
        if tone == GREEN or improved(entry["scorecard"], baseline["scorecard"]):
            streak = 0
            continue
        streak += 1
    return streak


def help_offered_for_streak(help_events: list[dict[str, Any]] | None, streak_start: str | None, week_start: str | None) -> bool:
    if not help_events or not streak_start:
        return False
    horizon = _add_days(week_start, 7) if week_start else None
    for event in help_events:
        offered = event.get("offeredOn") or event.get("offered_on")
        if not offered:
            continue
        if offered < streak_start:
            continue
        if horizon is not None and offered >= horizon:
            continue
        return True
    return False


def _add_days(value: str, days: int) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()
