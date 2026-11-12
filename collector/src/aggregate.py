"""Week aggregates and scorecard inputs for idea-usage-api/1."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

from . import presence as presence_mod
from . import thresholds as thresholds_mod

API_SCHEMA = "idea-usage-api/1"
DAY_SCHEMA = "idea-usage-day/1"
STALE_AFTER_HOURS = 48
HOURLY_CHART_MIN_WEEKLY_VIEWS = 20
HEADER_TIMEZONE = "Europe/Brussels"
SCHOOL_DAYS_EXPECTED = 5

ROLE_SINGULAR = ("admin", "teacher", "learner", "coach")


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def is_monday(value: str) -> bool:
    return parse_iso_date(value).weekday() == 0


def add_days(value: str, days: int) -> str:
    return (parse_iso_date(value) + timedelta(days=days)).isoformat()


def friday_of(week_start: str) -> str:
    return add_days(week_start, 4)


def week_dates(week_start: str) -> list[str]:
    return [add_days(week_start, i) for i in range(7)]


def school_dates(week_start: str) -> list[str]:
    return [add_days(week_start, i) for i in range(5)]


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_week_label(week_start: str, week_end: str) -> str:
    s, e = parse_iso_date(week_start), parse_iso_date(week_end)
    if s.month == e.month and s.year == e.year:
        return "Week of %s–%s %s %s" % (s.day, e.day, _MONTHS[e.month - 1], e.year)
    if s.year == e.year:
        return "Week of %s %s – %s %s %s" % (
            s.day, _MONTHS[s.month - 1], e.day, _MONTHS[e.month - 1], e.year
        )
    return "Week of %s %s %s – %s %s %s" % (
        s.day, _MONTHS[s.month - 1], s.year, e.day, _MONTHS[e.month - 1], e.year
    )


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def empty_scorecard() -> dict[str, Any]:
    return {
        "available": {
            "schoolDaysOn": None,
            "schoolDaysExpected": SCHOOL_DAYS_EXPECTED,
            "schoolHoursOnMinutes": None,
            "bootsPerSchoolDay": None,
            "longestGapMinutes": None,
        },
        "setup": {
            "classes": None,
            "learnersRegistered": None,
            "learnersEnrolled": None,
            "teachers": None,
            "admins": None,
            "nextcloudTeacherBeyondSeed": None,
            "nextcloudLearnerBeyondSeed": None,
            "kolibriCoachBeyondSeed": None,
        },
        "setupStatus": thresholds_mod.empty_setup_status(),
        "copies": {"kolibri": [], "nextcloud": [], "kiwix": []},
        "teachingCycle": {
            "lessonsCreated": None,
            "lessonsVisible": None,
            "quizzesCreated": None,
            "quizzesStarted": None,
            "learnerSessionsOnAssigned": None,
            "assignedShareOfLearnerVisits": None,
        },
        "learnersOperate": {
            "learnerSessions": None,
            "learnerMinutes": None,
            "coachSessions": None,
            "coachMinutes": None,
            "adminSessions": None,
            "adminMinutes": None,
            "guestVisits": None,
            "guestMinutes": None,
            "learnerShareOfMinutes": None,
        },
        "nextcloud": {
            "worksheetShares": None,
            "worksheetSharesTeacherLearner": None,
            "worksheetSharesAdmin": None,
            "editShares": None,
            "editSharesTeacherLearner": None,
            "editSharesAdmin": None,
            "fileDropLinks": None,
            "fileDropUploads": None,
            "fileDropUploadsTeacherLearner": None,
            "fileDropUploadsAdmin": None,
            "schoolFilesShares": None,
            "schoolFilesSharesTeacherLearner": None,
            "schoolFilesSharesAdmin": None,
            "officeOpens": None,
            "officeOpensTeacherLearner": None,
            "officeOpensAdmin": None,
            "officeDistinctDocuments": None,
            "officeRead": None,
            "officeEdit": None,
            "officeEstimatedMinutes": None,
            "documentsCreated": None,
            "documentsCreatedTeacherLearner": None,
            "documentsCreatedAdmin": None,
            "appsOpened": None,
        },
        "wikipedia": {
            "pageViewsOwn": None,
            "sessionsOwn": None,
            "distinctArticlesOwn": None,
        },
    }


def empty_census() -> dict[str, Any]:
    return {
        "classes": None,
        "classesDelta": None,
        "learnersRegistered": None,
        "learnersRegisteredDelta": None,
        "learnersEnrolled": None,
        "teachers": None,
        "teachersDelta": None,
        "admins": None,
        "coachesBeyondSeed": None,
    }


# Census keys copied from the hook. Each pair is (HTTP name, hook names in
# preference order). The shipped Kolibri hook (app-kolibri hooks/usage.sh)
# emits the singular ``learnerEnrolled`` / ``learnerDelta``; the PR #410 §7.6
# sketch names are still read so old day files parse.
_CENSUS_FLAT_KEYS = (
    ("classes", ("classes",)),
    ("classesDelta", ("classesDelta",)),
    ("learnersEnrolled", ("learnerEnrolled", "learnersEnrolled")),
    ("learnersRegisteredDelta", ("learnerDelta", "learnersRegisteredDelta")),
    ("teachersDelta", ("teachersDelta",)),
)


def kit_timezone(iana: str | None, utc_offset: str | None) -> dict[str, str]:
    offset = utc_offset or "+00:00"
    pretty = offset
    if pretty.endswith(":00") and len(pretty) >= 6:
        pretty = "UTC%s" % pretty[:3].replace("+0", "+").replace("-0", "-")
        if pretty.endswith("0") and len(pretty) > 4 and pretty[-2] != "0":
            pass
    label_offset = offset
    if iana:
        return {
            "timeZone": iana,
            "utcOffset": offset,
            "label": "kit local time (%s, UTC%s)" % (iana, offset[:3].lstrip("+") if False else _utc_label(offset)),
        }
    return {
        "timeZone": "",
        "utcOffset": offset,
        "label": "kit local time (UTC%s)" % _utc_label(offset),
    }


def _utc_label(offset: str) -> str:
    sign = offset[0] if offset[:1] in "+-" else "+"
    rest = offset[1:] if offset[:1] in "+-" else offset
    hours = rest.split(":")[0].lstrip("0") or "0"
    return "%s%s" % (sign, hours)


def offset_from_ts(value: str | None) -> str | None:
    if not value:
        return None
    if value.endswith("Z"):
        return "+00:00"
    if len(value) >= 6 and value[-6] in "+-" and value[-3] == ":":
        return value[-6:]
    return None


def freshness(last_pulled: str | None, now: datetime | None = None, stale_after_hours: int = STALE_AFTER_HOURS):
    if not last_pulled:
        return False, None
    ts = parse_ts(last_pulled)
    if ts is None:
        return False, None
    now = now or datetime.now(ts.tzinfo or timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stale = (now - ts) > timedelta(hours=stale_after_hours)
    return stale, (ts.date().isoformat() if stale else None)


def _load(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        return json.loads(payload)
    return payload or {}


def is_ok(row: Any) -> bool:
    payload = _load(row["payload"] if not isinstance(row, dict) or "payload" in row else row)
    status = None
    if hasattr(row, "keys"):
        try:
            status = row["hook_status"]
        except (KeyError, IndexError, TypeError):
            status = None
    if isinstance(row, dict):
        status = row.get("hook_status") or payload.get("hookStatus") or status
    return (status or payload.get("hookStatus") or "ok") == "ok"


def last_ok_payloads(rows: list[Any]) -> list[dict[str, Any]]:
    ok = [row for row in rows if is_ok(row)]
    return [_load(row["payload"]) for row in ok]


def group_by_instance(rows: list[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        payload = _load(row["payload"])
        key = row["instance"] if hasattr(row, "keys") and "instance" in row.keys() else (
            row.get("instance") if isinstance(row, dict) else None
        )
        key = key or payload.get("instance")
        if not key:
            continue
        grouped.setdefault(key, []).append(row)
    for items in grouped.values():
        items.sort(key=lambda r: r["day"] if not isinstance(r, dict) else r.get("day") or _load(r["payload"]).get("day") or "")
    return grouped


def _row_day(row: Any) -> str:
    if hasattr(row, "keys") and "day" in row.keys():
        return row["day"]
    if isinstance(row, dict):
        return row.get("day") or _load(row.get("payload")).get("day") or ""
    return ""


def _clock_of(payload: dict[str, Any]) -> dict[str, Any]:
    clock = payload.get("clock") or {}
    return {
        "synced": bool(clock.get("synced", True)),
        "correctedBoots": int(clock.get("correctedBoots") or 0),
    }


def week_clock(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Any unsynced day marks the whole week untrustworthy."""
    synced = True
    corrected = 0
    for payload in payloads:
        clock = _clock_of(payload)
        if not clock["synced"]:
            synced = False
        corrected += clock["correctedBoots"]
    return {"synced": synced, "correctedBoots": corrected}


def instance_envelope(rows: list[Any]) -> dict[str, Any]:
    last = rows[-1]
    last_payload = _load(last["payload"])
    ok_rows = [row for row in rows if is_ok(row)]
    ok_payloads = [_load(row["payload"]) for row in ok_rows]
    last_ok = ok_payloads[-1] if ok_payloads else None
    hook_status = last_payload.get("hookStatus") or (
        last["hook_status"] if hasattr(last, "keys") and "hook_status" in last.keys() else None
    ) or "ok"
    skip_reason = last_payload.get("skipReason")
    listed = last_payload.get("listed")
    if listed is None and hasattr(last, "keys") and "listed" in last.keys():
        listed = bool(last["listed"]) if last["listed"] is not None else None
    demo = bool(last_payload.get("demo")) if last_ok is None else bool(last_ok.get("demo"))
    instance = last_payload.get("instance") or (
        last["instance"] if hasattr(last, "keys") else last.get("instance")
    )
    return {
        "instance": instance,
        "instanceId": instance,
        "name": (last_ok or last_payload).get("name") or "",
        "app": (last_ok or last_payload).get("app") or last["app"] if hasattr(last, "keys") and "app" in last.keys() else (last_ok or last_payload).get("app"),
        "demo": demo,
        "listed": True if listed is None else bool(listed),
        "hookStatus": hook_status,
        "skipReason": skip_reason,
        "clock": week_clock(ok_payloads) if ok_payloads else None,
        "collectedAt": last_payload.get("collectedAt"),
        "flags": list((last_ok or {}).get("flags") or []),
        "_ok_payloads": ok_payloads,
        "_last_ok": last_ok,
    }


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def read_role_count(src: dict[str, Any] | None, role: str) -> dict[str, Any] | None:
    """Read {total, beyondSeed} from a hook RoleCount, or map a legacy integer / {users}."""
    if not src:
        return None
    aliases = [role]
    if role == "teacher":
        aliases.append("teachers")
    elif role == "learner":
        aliases.append("learners")
    elif role == "admin":
        aliases.append("admins")
    for key in aliases:
        item = src.get(key)
        if isinstance(item, dict):
            if "total" in item:
                beyond = item.get("beyondSeed")
                return {
                    "total": int(item["total"] or 0),
                    "beyondSeed": None if beyond is None else int(beyond),
                }
            if "users" in item:
                return {"total": int(item.get("users") or 0), "beyondSeed": None}
        n = _as_int(item)
        if n is not None:
            return {"total": n, "beyondSeed": None}
    return None


def role_total(setup: dict[str, Any], singular: str, *legacy: str) -> int | None:
    rc = read_role_count(setup, singular)
    if rc is not None:
        return rc["total"]
    for key in legacy:
        n = _as_int(setup.get(key))
        if n is not None:
            return n
    return None


def _census_from_setup(setup: dict[str, Any] | None) -> dict[str, Any]:
    out = empty_census()
    if not setup:
        return out
    for key, sources in _CENSUS_FLAT_KEYS:
        for src in sources:
            if src in setup:
                out[key] = _as_int(setup.get(src))
                break
    out["learnersRegistered"] = role_total(setup, "learner", "learnersRegistered")
    out["teachers"] = role_total(setup, "teacher", "teachers")
    out["admins"] = role_total(setup, "admin", "admins")
    out["coachesBeyondSeed"] = _coaches_beyond_seed(setup)
    return out


def _coaches_beyond_seed(setup: dict[str, Any]) -> int | None:
    """Kolibri coaches beyond the seed accounts (U-7 Set up, ruling 4).

    Prefers a ``setup.coach`` RoleCount (every account holding a coach role,
    admins included) if a future hook emits one. Today's hook emits
    ``setup.teacher`` = accounts whose *highest* role is coach, with seeds
    (``teacher1``/``teacher2``) excluded in ``beyondSeed``; an admin who also
    coaches is counted under ``admin`` there, so it is not seen as a coach.
    Null when the hook did not emit ``beyondSeed`` (old day files).
    """
    for role in ("coach", "teacher"):
        rc = read_role_count(setup, role)
        if rc is not None:
            return rc["beyondSeed"]
    return None


def clocks_trusted(instances: list[dict[str, Any]]) -> bool:
    """False only if a contributing ok-row this week had clock.synced=false.

    no-hook, unlisted-no-hook and skipped stub rows do not contribute, and
    neither do timeout / failed / invalid rows. A week with no contributing
    ok-rows is True (the documented shape is a boolean, not null). A missing
    or null clock on an ok-row does not taint the week.
    """
    for inst in instances:
        if inst.get("hookStatus") != "ok":
            continue
        clock = inst.get("clock")
        if clock is None:
            continue
        if not clock.get("synced", True):
            return False
    return True


def kolibri_week(rows: list[Any]) -> dict[str, Any]:
    env = instance_envelope(rows)
    ok_payloads = env.pop("_ok_payloads")
    last_ok = env.pop("_last_ok")
    env["app"] = "kolibri"
    if not ok_payloads:
        env.update({"setup": None, "signins": None, "guest": None, "teaching": None, "content": None})
        return env
    env["setup"] = _census_from_setup((last_ok or {}).get("setup"))
    signins = {
        role: {"users": 0, "usersBeyondSeed": None, "sessions": 0, "minutes": 0}
        for role in ("learner", "coach", "admin")
    }
    guest = {"visits": 0, "seconds": 0}
    teaching = {
        "lessonsCreated": 0, "lessonsVisible": 0,
        "quizzesCreated": 0, "quizzesStarted": 0, "quizzesEnded": 0,
    }
    content_map: dict[tuple, dict[str, Any]] = {}
    flags: set[str] = set(env["flags"])
    for payload in ok_payloads:
        flags.update(payload.get("flags") or [])
        raw = payload.get("signins") or {}
        for role in ("learner", "coach", "admin"):
            item = raw.get(role) or {}
            signins[role]["sessions"] += int(item.get("sessions") or 0)
            signins[role]["minutes"] += int(item.get("minutes") or 0)
            # Distinct accounts: the hook's daily ``total`` (old files: ``users``).
            # A weekly union needs ids the hook does not emit, so the week is
            # the max of the daily counts ("at least n"), like Kiwix articles.
            daily = item.get("total") if "total" in item else item.get("users")
            signins[role]["users"] = max(signins[role]["users"], int(daily or 0))
            beyond = _as_int(item.get("beyondSeed"))
            if beyond is not None:
                prev = signins[role]["usersBeyondSeed"]
                signins[role]["usersBeyondSeed"] = beyond if prev is None else max(prev, beyond)
        g = payload.get("guest") or {}
        guest["visits"] += int(g.get("visits") or 0)
        guest["seconds"] += int(g.get("seconds") or 0)
        tch = payload.get("teaching") or {}
        for key in ("lessonsCreated", "quizzesCreated", "quizzesStarted", "quizzesEnded"):
            teaching[key] += int(tch.get(key) or 0)
        teaching["lessonsVisible"] = int((last_ok.get("teaching") or {}).get("lessonsVisible") or 0)
        for row in payload.get("content") or []:
            key = (row.get("channel"), row.get("title"), row.get("kind"), row.get("role"), bool(row.get("assigned")))
            slot = content_map.setdefault(
                key,
                {
                    "channel": row.get("channel") or "",
                    "title": row.get("title") or "",
                    "kind": row.get("kind") or "",
                    "role": row.get("role") or "learner",
                    "visits": 0, "seconds": 0, "completions": 0,
                    "assigned": bool(row.get("assigned")),
                },
            )
            slot["visits"] += int(row.get("visits") or 0)
            slot["seconds"] += int(row.get("seconds") or 0)
            slot["completions"] += int(row.get("completions") or 0)
    env["flags"] = sorted(flags)
    env["signins"] = signins
    env["guest"] = guest
    env["teaching"] = teaching
    env["content"] = list(content_map.values())
    return env


def _login_users(logins: dict[str, Any], role: str) -> int:
    # Accept singular role keys and the older plural census-style keys.
    aliases = {role, role + "s", "admins" if role == "admin" else role}
    for key in aliases:
        item = logins.get(key)
        if isinstance(item, dict):
            return int(item.get("users") or 0)
        if isinstance(item, (int, float)):
            return int(item)
    return 0


def _by_group(office: dict[str, Any], role: str) -> int:
    by_group = office.get("byGroup") or {}
    if role in by_group:
        return int(by_group.get(role) or 0)
    plural = {"teacher": "teachers", "learner": "learners", "admin": "admin"}
    return int(by_group.get(plural.get(role, role)) or 0)


WORKFLOW_TOTAL_KEYS = (
    "worksheetShares", "editShares", "fileDropLinks", "fileDropUploads", "schoolFilesShares",
)
WORKFLOW_SPLIT_KEYS = (
    "worksheetShares", "editShares", "fileDropUploads", "schoolFilesShares",
)


def workflow_metric_split(workflows: dict[str, Any] | None, key: str) -> tuple[int | None, int | None]:
    """Teacher+learner and admin counts for one workflow metric.

    Same null rule as office_open_split: a missing or all-zero
    ``workflows.byGroup.<key>`` while the flat total is greater than 0
    is an unknown split. Both values are then None.
    """
    if not workflows:
        return None, None
    total = int(workflows.get(key) or 0)
    container = workflows.get("byGroup")
    by = container.get(key) if isinstance(container, dict) else None
    if not isinstance(by, dict):
        if total > 0:
            return None, None
        return 0, 0
    teacher = _by_group({"byGroup": by}, "teacher")
    learner = _by_group({"byGroup": by}, "learner")
    admin = _by_group({"byGroup": by}, "admin")
    if teacher + learner + admin == 0 and total > 0:
        return None, None
    return teacher + learner, admin


def office_open_split(office: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """Teacher+learner opens and admin opens, from office.byGroup.

    Old day files with no byGroup (or an empty / all-zero byGroup) while
    total ``opens`` is greater than 0 have an unknown split: both values
    are None. That way we never treat unattributed opens as teacher or
    learner activity, and we never invent an admin count of zero. A week
    with no opens is (0, 0).
    """
    if not office:
        return None, None
    opens = int(office.get("opens") or office.get("tokens") or 0)
    teacher = _by_group(office, "teacher")
    learner = _by_group(office, "learner")
    admin = _by_group(office, "admin")
    if teacher + learner + admin == 0 and opens > 0:
        return None, None
    return teacher + learner, admin


def nextcloud_week(rows: list[Any]) -> dict[str, Any]:
    env = instance_envelope(rows)
    ok_payloads = env.pop("_ok_payloads")
    last_ok = env.pop("_last_ok")
    env["app"] = "nextcloud"
    env.pop("flags", None)
    if not ok_payloads:
        env.update({
            "setup": None, "logins": None, "office": None, "appsOpened": None, "workflows": None,
            "documentsCreated": None, "documentsCreatedByGroup": None,
        })
        return env
    setup_src = (last_ok or {}).get("setup") or {}
    env["setup"] = {
        "admin": read_role_count(setup_src, "admin") or {"total": 0, "beyondSeed": None},
        "teacher": read_role_count(setup_src, "teacher") or {"total": 0, "beyondSeed": None},
        "learner": read_role_count(setup_src, "learner") or {"total": 0, "beyondSeed": None},
        "otherGroups": setup_src.get("otherGroups") or {},
    }
    logins = {role: {"total": 0, "beyondSeed": 0} for role in ("admin", "teacher", "learner")}
    beyond_known = {role: True for role in logins}
    office = {
        "opens": 0, "distinctDocuments": 0, "read": 0, "edit": 0,
        "estimatedMinutes": None,
        "byGroup": {"admin": 0, "teacher": 0, "learner": 0},
        "mime": {"text": 0, "sheet": 0, "slides": 0},
    }
    # appsOpened is null until a hook actually measures it (app-nextcloud
    # omits it until the IDEA app-open counter ships). ``{}`` means measured,
    # nothing opened.
    apps: dict[str, int] | None = None
    docs_created: int | None = None
    docs_by_group: dict[str, int] | None = None
    workflows = {key: 0 for key in WORKFLOW_TOTAL_KEYS}
    workflows["byGroup"] = {key: {"admin": 0, "teacher": 0, "learner": 0} for key in WORKFLOW_SPLIT_KEYS}
    est_sum = 0
    has_est = False
    for payload in ok_payloads:
        raw_logins = payload.get("logins") or {}
        for role in ("admin", "teacher", "learner"):
            rc = read_role_count(raw_logins, role) or {"total": 0, "beyondSeed": None}
            logins[role]["total"] += rc["total"]
            if rc["beyondSeed"] is None:
                beyond_known[role] = False
            else:
                logins[role]["beyondSeed"] += rc["beyondSeed"]
        off = payload.get("office") or {}
        office["opens"] += int(off.get("opens") or off.get("tokens") or 0)
        office["read"] += int(off.get("read") or 0)
        office["edit"] += int(off.get("edit") or 0)
        est = off.get("estimatedMinutes")
        if isinstance(est, (int, float)):
            has_est = True
            est_sum += int(est)
        for role in ("admin", "teacher", "learner"):
            office["byGroup"][role] += _by_group(off, role)
        mime = off.get("mime") or {}
        for kind in ("text", "sheet", "slides"):
            office["mime"][kind] += int(mime.get(kind) or 0)
        opened = payload.get("appsOpened")
        if isinstance(opened, dict):
            apps = apps if apps is not None else {}
            for app_id, count in opened.items():
                apps[app_id] = apps.get(app_id, 0) + int(count or 0)
        elif isinstance(opened, list):
            apps = apps if apps is not None else {}
            for item in opened:
                app_id = item.get("appId")
                if app_id:
                    apps[app_id] = apps.get(app_id, 0) + int(item.get("opens") or 0)
        created, created_by = _documents_created(payload)
        if created is not None:
            docs_created = (docs_created or 0) + created
        if created_by is not None:
            docs_by_group = docs_by_group or {"admin": 0, "teacher": 0, "learner": 0}
            for role in docs_by_group:
                docs_by_group[role] += created_by[role]
        wf = payload.get("workflows") or {}
        for key in WORKFLOW_TOTAL_KEYS:
            workflows[key] += int(wf.get(key) or 0)
        # Older draft used fileDrops as a single field.
        if "fileDrops" in wf and not wf.get("fileDropUploads"):
            workflows["fileDropUploads"] += int(wf.get("fileDrops") or 0)
        raw_bg = wf.get("byGroup") if isinstance(wf.get("byGroup"), dict) else {}
        for key in WORKFLOW_SPLIT_KEYS:
            src = raw_bg.get(key) if isinstance(raw_bg.get(key), dict) else {}
            for role in ("admin", "teacher", "learner"):
                workflows["byGroup"][key][role] += _by_group({"byGroup": src}, role)
    for role in logins:
        if not beyond_known[role]:
            logins[role]["beyondSeed"] = None
    last_ok_office = (last_ok or {}).get("office") or {}
    office["distinctDocuments"] = int(last_ok_office.get("distinctDocuments") or 0)
    office["estimatedMinutes"] = est_sum if has_est else None
    env["logins"] = logins
    env["office"] = office
    env["appsOpened"] = apps
    env["workflows"] = workflows
    env["documentsCreated"] = docs_created
    env["documentsCreatedByGroup"] = docs_by_group
    return env


def _documents_created(payload: dict[str, Any]) -> tuple[int | None, dict[str, int] | None]:
    """Office documents created that day, from a future app-nextcloud hook.

    Hook contract (draft, app-nextcloud counter issue): ``documents: {created,
    byGroup: {admin, teacher, learner}}``. Flat ``documentsCreated`` /
    ``documentsCreatedByGroup`` are accepted too. (None, None) when absent.
    """
    docs = payload.get("documents") if isinstance(payload.get("documents"), dict) else {}
    created = _as_int(docs.get("created")) if "created" in docs else _as_int(payload.get("documentsCreated"))
    by = docs.get("byGroup") if isinstance(docs.get("byGroup"), dict) else payload.get("documentsCreatedByGroup")
    by_group = None
    if isinstance(by, dict):
        by_group = {role: _by_group({"byGroup": by}, role) for role in ("admin", "teacher", "learner")}
    return created, by_group


def kiwix_week(rows: list[Any]) -> dict[str, Any]:
    env = instance_envelope(rows)
    ok_payloads = env.pop("_ok_payloads")
    env.pop("_last_ok", None)
    env.pop("flags", None)
    env["app"] = "kiwix"
    if not ok_payloads:
        env.update({
            "pageViews": None, "distinctArticles": None, "sessions": None,
            "topArticles": None, "byHour": None,
        })
        return env
    page_views = sessions = 0
    distinct = 0
    by_hour = [0] * 24
    titles: dict[str, int] = {}
    for payload in ok_payloads:
        page_views += int(payload.get("pageViews") or 0)
        sessions += int(payload.get("sessions") or 0)
        distinct = max(distinct, int(payload.get("distinctArticles") or 0))
        hours = payload.get("byHour") or []
        for i in range(min(24, len(hours))):
            by_hour[i] += int(hours[i] or 0)
        for row in payload.get("topArticles") or []:
            title = row.get("title") or ""
            titles[title] = titles.get(title, 0) + int(row.get("views") or 0)
    top = sorted(({"title": k, "views": v} for k, v in titles.items() if k), key=lambda x: (-x["views"], x["title"]))[:50]
    env.update({
        "pageViews": page_views,
        "distinctArticles": distinct,
        "sessions": sessions,
        "topArticles": top,
        "byHour": by_hour,
    })
    return env


def discovered_instance(rows: list[Any]) -> dict[str, Any]:
    week = instance_envelope(rows)
    week.pop("_ok_payloads", None)
    week.pop("_last_ok", None)
    app = week.get("app") or "other"
    if app not in ("kolibri", "nextcloud", "kiwix"):
        app = "other"
    note = ""
    if week.get("demo"):
        note = "Tutorial Demo — kept on its own line"
    elif not week.get("listed"):
        if week.get("hookStatus") == "ok":
            note = "Engine-unlisted container; hook borrowed from the matching App version"
        elif week.get("hookStatus") == "unlisted-no-hook":
            note = "Engine-unlisted container; no matching hook"
    return {
        "instance": week.get("instance"),
        "instanceId": week.get("instance"),
        "name": week.get("name") or "",
        "app": app,
        "demo": week.get("demo"),
        "listed": week.get("listed"),
        "hookStatus": week.get("hookStatus"),
        "skipReason": week.get("skipReason"),
        "clock": week.get("clock"),
        "collectedAt": week.get("collectedAt"),
        "port": None,
        "note": note,
    }


def own_instances(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if not item.get("demo")]


# idea#462 ruling 2 (Steve, 2026-11-12): census and Set up inputs are the MAX
# across the school's own copies, not the sum, because two own copies are most
# often clones of the same school database (summing would double-count the
# same classes and accounts). Activity (sessions, minutes, shares, opens) is
# still summed over the same copies: each copy logs its own events.
CENSUS_ACROSS_COPIES = "max"


def _combine(values: list[int | None]) -> int | None:
    known = [int(v) for v in values if v is not None]
    if not known:
        return None
    return max(known) if CENSUS_ACROSS_COPIES == "max" else sum(known)


def own_copies(items: list[dict[str, Any]], measured_key: str = "setup") -> list[dict[str, Any]]:
    """Own (non-demo) copies with at least one ok day this week.

    The one copy set used for census, activity sums and setupStatus inputs
    (idea#462 item 5). Order is by instance id so results are deterministic.
    """
    return sorted(
        (item for item in own_instances(items) if item.get(measured_key) is not None),
        key=lambda item: item.get("instance") or "",
    )


CENSUS_KEYS = tuple(empty_census().keys())


def school_census(kolibri: list[dict[str, Any]]) -> dict[str, Any]:
    """School census (Q3) from the own Kolibri copies, combined per field."""
    copies = own_copies(kolibri)
    out = empty_census()
    if not copies:
        return out
    for key in CENSUS_KEYS:
        out[key] = _combine([(c.get("setup") or {}).get(key) for c in copies])
    return out


def _nextcloud_setup_inputs(inst: dict[str, Any]) -> dict[str, Any] | None:
    setup = inst.get("setup")
    if setup is None:
        return None
    teacher = read_role_count(setup, "teacher") or {}
    learner = read_role_count(setup, "learner") or {}
    return {"teacherBeyondSeed": teacher.get("beyondSeed"), "learnerBeyondSeed": learner.get("beyondSeed")}


def _setup_copies(items: list[dict[str, Any]], inputs_of) -> list[tuple[str, dict[str, Any] | None]]:
    """``(instanceId, inputs)`` pairs for one app's U-7 Set up part.

    Only the school's own copies count, and only those with an ok day this
    week (the same ``own_copies`` set the census and ``scorecard.copies``
    use). A copy with no ok day (e.g. a listed, non-hooked
    ``nextcloud-files-b-001``) has no known value, so it must not turn a part
    that the measured copies already decide into "unknown" (1.2 acceptance,
    idea#462). Only when NO own copy has an ok day are the unmeasured own
    copies passed through as unknown (inputs None), so the part is unknown
    rather than "noOwn…": the school does have a copy, it just was not read.
    """
    measured = own_copies(items)
    if measured:
        return [(item.get("instance") or "", inputs_of(item)) for item in measured]
    return [
        (item.get("instance") or "", None)
        for item in sorted(own_instances(items), key=lambda x: x.get("instance") or "")
    ]


def setup_status_from_weeks(
    kolibri: list[dict[str, Any]], nextcloud: list[dict[str, Any]], kiwix: list[dict[str, Any]]
) -> dict[str, Any]:
    """``scorecard.setupStatus`` from all instance weeks (own copies judged per copy)."""
    has_data = any(k.get("setup") is not None for k in kolibri) or any(
        n.get("setup") is not None for n in nextcloud
    ) or any(z.get("pageViews") is not None for z in kiwix)
    k_copies = _setup_copies(kolibri, lambda k: k.get("setup"))
    n_copies = _setup_copies(nextcloud, _nextcloud_setup_inputs)
    return thresholds_mod.setup_status(k_copies, n_copies, has_data)


def scorecard_from_weeks(
    kolibri: list[dict[str, Any]],
    nextcloud: list[dict[str, Any]],
    kiwix: list[dict[str, Any]],
    presence_days: list[dict[str, Any]],
    week_start: str,
) -> dict[str, Any]:
    card = empty_scorecard()
    school = school_dates(week_start)
    by_day = {row["day"]: row for row in presence_days}
    if presence_days:
        on_days = 0
        school_minutes = 0
        boots = []
        longest = 0
        any_known = False
        for day in school:
            row = by_day.get(day)
            if row and row.get("schoolHoursOnMinutes"):
                on_days += 1
            school_minutes += int((row or {}).get("schoolHoursOnMinutes") or 0)
            boots.append(int((row or {}).get("boots") or 0) if row else 0)
            longest = max(longest, int((row or {}).get("longestGapMinutes") or 0))
            if row:
                any_known = True
        if any_known:
            card["available"]["schoolDaysOn"] = on_days
            card["available"]["schoolHoursOnMinutes"] = school_minutes
            card["available"]["bootsPerSchoolDay"] = boots
            card["available"]["longestGapMinutes"] = longest

    card["setupStatus"] = setup_status_from_weeks(kolibri, nextcloud, kiwix)
    own_k = own_copies(kolibri)
    card["copies"]["kolibri"] = [k.get("instance") for k in own_k]
    if own_k:
        census = school_census(kolibri)
        for key in ("classes", "learnersRegistered", "learnersEnrolled", "teachers", "admins"):
            card["setup"][key] = census[key]
        card["setup"]["kolibriCoachBeyondSeed"] = census["coachesBeyondSeed"]
        teaching = {
            "lessonsCreated": 0, "lessonsVisible": 0,
            "quizzesCreated": 0, "quizzesStarted": 0,
        }
        assigned_visits = 0
        learner_visits = 0
        sessions = {"learner": 0, "coach": 0, "admin": 0}
        minutes = {"learner": 0, "coach": 0, "admin": 0}
        guest_visits = guest_minutes = 0
        for inst in own_k:
            tch = inst.get("teaching") or {}
            for key in teaching:
                if key == "lessonsVisible":
                    teaching[key] = max(teaching[key], int(tch.get(key) or 0))
                else:
                    teaching[key] += int(tch.get(key) or 0)
            for row in inst.get("content") or []:
                if row.get("role") == "learner":
                    learner_visits += int(row.get("visits") or 0)
                    if row.get("assigned"):
                        assigned_visits += int(row.get("visits") or 0)
            raw = inst.get("signins") or {}
            for role in sessions:
                item = raw.get(role) or {}
                sessions[role] += int(item.get("sessions") or 0)
                minutes[role] += int(item.get("minutes") or 0)
            guest = inst.get("guest") or {}
            guest_visits += int(guest.get("visits") or 0)
            guest_minutes += int(guest.get("seconds") or 0) // 60
        card["teachingCycle"].update({
            "lessonsCreated": teaching["lessonsCreated"],
            "lessonsVisible": teaching["lessonsVisible"],
            "quizzesCreated": teaching["quizzesCreated"],
            "quizzesStarted": teaching["quizzesStarted"],
            "learnerSessionsOnAssigned": assigned_visits,
            "assignedShareOfLearnerVisits": (
                assigned_visits / learner_visits if learner_visits else None
            ),
        })
        total_min = minutes["learner"] + minutes["coach"] + minutes["admin"]
        card["learnersOperate"].update({
            "learnerSessions": sessions["learner"],
            "learnerMinutes": minutes["learner"],
            "coachSessions": sessions["coach"],
            "coachMinutes": minutes["coach"],
            "adminSessions": sessions["admin"],
            "adminMinutes": minutes["admin"],
            "guestVisits": guest_visits,
            "guestMinutes": guest_minutes,
            "learnerShareOfMinutes": (minutes["learner"] / total_min) if total_min else None,
        })

    own_n = own_copies(nextcloud)
    card["copies"]["nextcloud"] = [n.get("instance") for n in own_n]
    if own_n:
        teacher_values: list[int | None] = []
        learner_values: list[int | None] = []
        docs_created: int | None = None
        docs_tl = docs_admin = 0
        has_docs_split = False
        apps: dict[str, int] | None = None
        worksheet = edit_shares = file_drop_links = file_drop_uploads = school_files = 0
        split_tl = {key: 0 for key in WORKFLOW_SPLIT_KEYS}
        split_admin = {key: 0 for key in WORKFLOW_SPLIT_KEYS}
        has_workflow_split = {key: False for key in WORKFLOW_SPLIT_KEYS}
        office_opens = office_distinct = office_read = office_edit = 0
        office_tl = office_admin = 0
        has_office_split = False
        office_est = 0
        has_est = False
        for inst in own_n:
            inputs = _nextcloud_setup_inputs(inst) or {}
            teacher_values.append(inputs.get("teacherBeyondSeed"))
            learner_values.append(inputs.get("learnerBeyondSeed"))
            if inst.get("documentsCreated") is not None:
                docs_created = (docs_created or 0) + int(inst["documentsCreated"])
                by = inst.get("documentsCreatedByGroup")
                if isinstance(by, dict) and (sum(int(v or 0) for v in by.values()) > 0 or not inst["documentsCreated"]):
                    has_docs_split = True
                    docs_tl += int(by.get("teacher") or 0) + int(by.get("learner") or 0)
                    docs_admin += int(by.get("admin") or 0)
            if isinstance(inst.get("appsOpened"), dict):
                apps = apps if apps is not None else {}
                for app_id, count in inst["appsOpened"].items():
                    apps[app_id] = apps.get(app_id, 0) + int(count or 0)
            wf = inst.get("workflows") or {}
            worksheet += int(wf.get("worksheetShares") or 0)
            edit_shares += int(wf.get("editShares") or 0)
            file_drop_links += int(wf.get("fileDropLinks") or 0)
            file_drop_uploads += int(wf.get("fileDropUploads") or wf.get("fileDrops") or 0)
            school_files += int(wf.get("schoolFilesShares") or 0)
            for key in WORKFLOW_SPLIT_KEYS:
                teacher_learner, admin_count = workflow_metric_split(wf, key)
                if teacher_learner is not None:
                    has_workflow_split[key] = True
                    split_tl[key] += teacher_learner
                    split_admin[key] += int(admin_count or 0)
            off = inst.get("office") or {}
            office_opens += int(off.get("opens") or 0)
            teacher_learner, admin_opens = office_open_split(off)
            if teacher_learner is not None:
                has_office_split = True
                office_tl += teacher_learner
                office_admin += int(admin_opens or 0)
            # Sum across the school's own Nextcloud instances: document ids
            # are salted per instance, so two own Nextclouds hold different documents.
            office_distinct += int(off.get("distinctDocuments") or 0)
            office_read += int(off.get("read") or 0)
            office_edit += int(off.get("edit") or 0)
            if isinstance(off.get("estimatedMinutes"), (int, float)):
                has_est = True
                office_est += int(off["estimatedMinutes"])
        card["setup"]["nextcloudTeacherBeyondSeed"] = _combine(teacher_values)
        card["setup"]["nextcloudLearnerBeyondSeed"] = _combine(learner_values)
        def _split_fields(key: str) -> tuple[int | None, int | None]:
            if has_workflow_split[key]:
                return split_tl[key], split_admin[key]
            return None, None

        ws_tl, ws_admin = _split_fields("worksheetShares")
        ed_tl, ed_admin = _split_fields("editShares")
        fd_tl, fd_admin = _split_fields("fileDropUploads")
        sf_tl, sf_admin = _split_fields("schoolFilesShares")
        card["nextcloud"].update({
            "worksheetShares": worksheet,
            "worksheetSharesTeacherLearner": ws_tl,
            "worksheetSharesAdmin": ws_admin,
            "editShares": edit_shares,
            "editSharesTeacherLearner": ed_tl,
            "editSharesAdmin": ed_admin,
            "fileDropLinks": file_drop_links,
            "fileDropUploads": file_drop_uploads,
            "fileDropUploadsTeacherLearner": fd_tl,
            "fileDropUploadsAdmin": fd_admin,
            "schoolFilesShares": school_files,
            "schoolFilesSharesTeacherLearner": sf_tl,
            "schoolFilesSharesAdmin": sf_admin,
            "officeOpens": office_opens,
            "officeOpensTeacherLearner": office_tl if has_office_split else None,
            "officeOpensAdmin": office_admin if has_office_split else None,
            "officeDistinctDocuments": office_distinct,
            "officeRead": office_read,
            "officeEdit": office_edit,
            "officeEstimatedMinutes": office_est if has_est else None,
            # Display only (ruling 3): not part of U-7 line 5.
            "documentsCreated": docs_created,
            "documentsCreatedTeacherLearner": docs_tl if has_docs_split else None,
            "documentsCreatedAdmin": docs_admin if has_docs_split else None,
            "appsOpened": apps,
        })

    own_z = own_copies(kiwix, "pageViews")
    card["copies"]["kiwix"] = [z.get("instance") for z in own_z]
    if own_z:
        card["wikipedia"].update({
            "pageViewsOwn": sum(int(z.get("pageViews") or 0) for z in own_z),
            "sessionsOwn": sum(int(z.get("sessions") or 0) for z in own_z),
            "distinctArticlesOwn": max((int(z.get("distinctArticles") or 0) for z in own_z), default=0),
        })
    return card


def format_school_hours(minutes: int) -> str:
    hours = minutes / 60
    if abs(hours - round(hours)) < 1e-9:
        return "%d h" % int(round(hours))
    text = ("%.1f" % hours).rstrip("0").rstrip(".")
    return "%s h" % text


def presence_summary(presence_days: list[dict[str, Any]], week_start: str) -> str | None:
    """Short operator sentence, or None. Never an empty string."""
    school = school_dates(week_start)
    by_day = {row["day"]: row for row in presence_days}
    if not any(day in by_day for day in school):
        return None
    on_days = 0
    minutes = 0
    for day in school:
        row = by_day.get(day)
        mins = int((row or {}).get("schoolHoursOnMinutes") or 0)
        minutes += mins
        if row and mins > 0:
            on_days += 1
    return "On %d of %d school days, %s in school hours" % (
        on_days,
        SCHOOL_DAYS_EXPECTED,
        format_school_hours(minutes),
    )


def headlines_from(scorecard: dict[str, Any]) -> dict[str, Any]:
    lo = scorecard["learnersOperate"]
    minutes = None
    parts = [lo.get("learnerMinutes"), lo.get("coachMinutes"), lo.get("adminMinutes")]
    if any(p is not None for p in parts):
        minutes = sum(int(p or 0) for p in parts)
    return {
        "classes": scorecard["setup"]["classes"],
        "learnersRegistered": scorecard["setup"]["learnersRegistered"],
        "teachers": scorecard["setup"]["teachers"],
        "kolibriMinutes": minutes,
    }


def school_note(kit_note: str, instances: list[dict[str, Any]], has_usage: bool) -> str:
    if kit_note:
        return kit_note
    if not has_usage:
        return "Not installed yet"
    demos = any(item.get("demo") for item in instances)
    owns = any(not item.get("demo") for item in instances)
    if owns and demos:
        return "own apps + Demo"
    if demos:
        return "Demo"
    return ""


def _kit_identity(kit: Any) -> tuple[str, str, str]:
    return kit["engine"], kit["school"], kit["deployment_id"]


def _suggestion(kit: Any, message: str) -> dict[str, Any]:
    engine, school, deployment_id = _kit_identity(kit)
    return {
        "deploymentId": deployment_id,
        "engine": engine,
        "school": school,
        "message": message,
    }


def help_status_for(
    card: dict[str, Any],
    kit: Any,
    scorecard: dict[str, Any],
    presence_days: list[dict[str, Any]] | None = None,
    thresholds: dict[str, Any] | None = None,
    weekly: list[dict[str, Any]] | None = None,
    help_events: list[dict[str, Any]] | None = None,
    week_start: str | None = None,
) -> dict[str, Any]:
    """Banner suggestion plus unused flag, using the shared U-7 thresholds.

    Grey weeks never count toward the amber or unused streaks. Colours are
    computed here only for those streaks; scorecard responses stay raw inputs.
    ``presence_days`` is accepted for call-site compatibility and is not used:
    school-hour availability is read from the scorecard's ``schoolDaysOn``.
    """
    del presence_days
    thresholds = thresholds or thresholds_mod.DEFAULTS
    engine, school, _deployment_id = _kit_identity(kit)
    monitoring = kit["monitoring_enabled"]
    if monitoring == 0:
        return {"suggestion": None, "unused": False}
    if weekly is None:
        weekly = [{
            "weekStart": week_start,
            "scorecard": scorecard,
            "hasUsageData": card.get("hasUsageData"),
        }]
    unused_count = thresholds_mod.unused_streak(weekly, help_events, thresholds)
    unused = unused_count >= thresholds["unusedAfterHelpWeeks"]
    if not card.get("hasUsageData") and not kit["last_pulled"]:
        return {
            "suggestion": _suggestion(
                kit,
                "%s (%s) has no pulled usage data yet — offer help checking the usage export."
                % (engine, school),
            ),
            "unused": unused,
        }
    streak, streak_start = thresholds_mod.amber_streak(weekly, thresholds)
    already = thresholds_mod.help_offered_for_streak(help_events, streak_start, week_start)
    suggestion = None
    if streak >= thresholds["helpAfterAmberWeeks"] and not already:
        suggestion = _suggestion(
            kit,
            "%s (%s) has been below the scorecard thresholds for %d consecutive school weeks — offer help."
            % (engine, school, streak),
        )
    return {"suggestion": suggestion, "unused": unused}


def help_suggestions_for(
    card: dict[str, Any],
    kit: Any,
    scorecard: dict[str, Any],
    presence_days: list[dict[str, Any]] | None = None,
    thresholds: dict[str, Any] | None = None,
    weekly: list[dict[str, Any]] | None = None,
    help_events: list[dict[str, Any]] | None = None,
    week_start: str | None = None,
) -> dict[str, Any] | None:
    """Server-owned fleet banner item, or None."""
    return help_status_for(
        card,
        kit,
        scorecard,
        presence_days,
        thresholds=thresholds,
        weekly=weekly,
        help_events=help_events,
        week_start=week_start,
    )["suggestion"]


def tzinfo_from_offset(offset: str | None) -> tzinfo:
    if not offset:
        return timezone.utc
    sign = 1 if offset[0] != "-" else -1
    body = offset[1:] if offset[0] in "+-" else offset
    hours, minutes = body.split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
