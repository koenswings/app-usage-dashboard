"""Week aggregates and scorecard inputs for idea-usage-api/1."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any

from . import presence as presence_mod

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
        },
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
            "editShares": None,
            "fileDropLinks": None,
            "fileDropUploads": None,
            "schoolFilesShares": None,
            "officeOpens": None,
            "officeDistinctDocuments": None,
            "officeRead": None,
            "officeEdit": None,
            "officeEstimatedMinutes": None,
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
    }


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
        "clock": week_clock(ok_payloads or [last_payload]),
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
    for key in ("classes", "classesDelta", "learnersEnrolled", "learnersRegisteredDelta", "teachersDelta"):
        if key in setup:
            out[key] = _as_int(setup.get(key))
    out["learnersRegistered"] = role_total(setup, "learner", "learnersRegistered")
    out["teachers"] = role_total(setup, "teacher", "teachers")
    out["admins"] = role_total(setup, "admin", "admins")
    return out


def clocks_trusted(instances: list[dict[str, Any]]) -> bool:
    """False when any instance clock is present and unsynced (Pixel weekClockTrusted)."""
    for inst in instances:
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
        "learner": {"users": 0, "sessions": 0, "minutes": 0},
        "coach": {"users": 0, "sessions": 0, "minutes": 0},
        "admin": {"users": 0, "sessions": 0, "minutes": 0},
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
            signins[role]["users"] = max(signins[role]["users"], int(item.get("users") or 0))
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


def nextcloud_week(rows: list[Any]) -> dict[str, Any]:
    env = instance_envelope(rows)
    ok_payloads = env.pop("_ok_payloads")
    last_ok = env.pop("_last_ok")
    env["app"] = "nextcloud"
    env.pop("flags", None)
    if not ok_payloads:
        env.update({"setup": None, "logins": None, "office": None, "appsOpened": None, "workflows": None})
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
    apps: dict[str, int] = {}
    workflows = {
        "worksheetShares": 0, "editShares": 0,
        "fileDropLinks": 0, "fileDropUploads": 0, "schoolFilesShares": 0,
    }
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
            for app_id, count in opened.items():
                apps[app_id] = apps.get(app_id, 0) + int(count or 0)
        elif isinstance(opened, list):
            for item in opened:
                app_id = item.get("appId")
                if app_id:
                    apps[app_id] = apps.get(app_id, 0) + int(item.get("opens") or 0)
        wf = payload.get("workflows") or {}
        for key in workflows:
            workflows[key] += int(wf.get(key) or 0)
        # Older draft used fileDrops as a single field.
        if "fileDrops" in wf and not wf.get("fileDropUploads"):
            workflows["fileDropUploads"] += int(wf.get("fileDrops") or 0)
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
    return env


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

    own_k = own_instances([k for k in kolibri if k.get("setup") is not None])
    if own_k:
        setup = own_k[0]["setup"]
        card["setup"]["classes"] = setup.get("classes")
        card["setup"]["learnersRegistered"] = setup.get("learnersRegistered")
        card["setup"]["learnersEnrolled"] = setup.get("learnersEnrolled")
        card["setup"]["teachers"] = setup.get("teachers")
        card["setup"]["admins"] = setup.get("admins")
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

    own_n = own_instances([n for n in nextcloud if n.get("setup") is not None])
    if own_n:
        teacher_beyond = learner_beyond = None
        worksheet = edit_shares = file_drop_links = file_drop_uploads = school_files = 0
        office_opens = office_distinct = office_read = office_edit = 0
        office_est = 0
        has_est = False
        for inst in own_n:
            setup = inst.get("setup") or {}
            teacher_rc = read_role_count(setup, "teacher")
            learner_rc = read_role_count(setup, "learner")
            if teacher_beyond is None and teacher_rc and teacher_rc.get("beyondSeed") is not None:
                teacher_beyond = int(teacher_rc["beyondSeed"])
            if learner_beyond is None and learner_rc and learner_rc.get("beyondSeed") is not None:
                learner_beyond = int(learner_rc["beyondSeed"])
            wf = inst.get("workflows") or {}
            worksheet += int(wf.get("worksheetShares") or 0)
            edit_shares += int(wf.get("editShares") or 0)
            file_drop_links += int(wf.get("fileDropLinks") or 0)
            file_drop_uploads += int(wf.get("fileDropUploads") or wf.get("fileDrops") or 0)
            school_files += int(wf.get("schoolFilesShares") or 0)
            off = inst.get("office") or {}
            office_opens += int(off.get("opens") or 0)
            # Sum across the school's own Nextcloud instances: document ids
            # are salted per instance, so two own Nextclouds hold different documents.
            office_distinct += int(off.get("distinctDocuments") or 0)
            office_read += int(off.get("read") or 0)
            office_edit += int(off.get("edit") or 0)
            if isinstance(off.get("estimatedMinutes"), (int, float)):
                has_est = True
                office_est += int(off["estimatedMinutes"])
        card["setup"]["nextcloudTeacherBeyondSeed"] = teacher_beyond
        card["setup"]["nextcloudLearnerBeyondSeed"] = learner_beyond
        card["nextcloud"].update({
            "worksheetShares": worksheet,
            "editShares": edit_shares,
            "fileDropLinks": file_drop_links,
            "fileDropUploads": file_drop_uploads,
            "schoolFilesShares": school_files,
            "officeOpens": office_opens,
            "officeDistinctDocuments": office_distinct,
            "officeRead": office_read,
            "officeEdit": office_edit,
            "officeEstimatedMinutes": office_est if has_est else None,
        })

    own_z = own_instances([z for z in kiwix if z.get("pageViews") is not None])
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


def help_suggestions_for(card: dict[str, Any], kit: Any, scorecard: dict[str, Any]) -> dict[str, Any] | None:
    """Conservative, server-owned banner items. Always phrased as 'offer help'."""
    engine = kit["engine"]
    school = kit["school"]
    deployment_id = kit["deployment_id"]
    monitoring = kit["monitoring_enabled"]
    if monitoring == 0:
        return None
    if not card.get("hasUsageData"):
        if kit["last_pulled"]:
            return None
        return {
            "deploymentId": deployment_id,
            "engine": engine,
            "school": school,
            "message": "%s (%s) has no pulled usage data yet — offer help checking the usage export." % (engine, school),
        }
    school_on = (scorecard.get("available") or {}).get("schoolDaysOn")
    learner_sessions = (scorecard.get("learnersOperate") or {}).get("learnerSessions")
    if school_on and school_on >= 1 and learner_sessions == 0:
        return {
            "deploymentId": deployment_id,
            "engine": engine,
            "school": school,
            "message": (
                "%s (%s) shows a school-day power pattern but almost no learner activity this week "
                "— offer help on tutorial chapters 3.3–3.4 and 4."
            ) % (engine, school),
        }
    if school_on == 0 and scorecard.get("available", {}).get("schoolHoursOnMinutes") == 0:
        return {
            "deploymentId": deployment_id,
            "engine": engine,
            "school": school,
            "message": "%s (%s) was not on during school hours this week — offer help." % (engine, school),
        }
    return None


def tzinfo_from_offset(offset: str | None) -> tzinfo:
    if not offset:
        return timezone.utc
    sign = 1 if offset[0] != "-" else -1
    body = offset[1:] if offset[0] in "+-" else offset
    hours, minutes = body.split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
