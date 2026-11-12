"""HTTP API: idea-usage-api/1 (Pixel #415 after Axle's corrections)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from . import aggregate as agg
from . import auth
from . import buildinfo
from . import db
from . import presence as presence_mod
from . import thresholds as thresholds_mod

PUBLIC_PATHS = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/session"),
    ("POST", "/api/v1/session"),
    ("DELETE", "/api/v1/session"),
}


def error_body(code: str, message: str, details=None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def _monitoring_enabled(kit) -> bool:
    value = kit["monitoring_enabled"]
    return value != 0 if value is not None else False


def _kit_tz(conn, kit, week_start: str | None = None) -> dict[str, str]:
    iana = kit["timezone"] or None
    offset = presence_mod.offset_at(iana, week_start)
    if offset is None:
        row = conn.execute(
            "SELECT ts FROM presence_samples WHERE engine = ? ORDER BY ts DESC LIMIT 1",
            (kit["engine"],),
        ).fetchone()
        if row:
            offset = agg.offset_from_ts(row["ts"])
    return agg.kit_timezone(iana, offset)


def _summaries(conn, engine: str, week_start: str):
    days = agg.week_dates(week_start)
    rows = conn.execute(
        """SELECT * FROM daily_summaries
           WHERE engine = ? AND day >= ? AND day <= ?
           ORDER BY day, instance""",
        (engine, days[0], days[-1]),
    ).fetchall()
    return rows


def _weeks_available(conn) -> list[str]:
    """Mondays that have stored daily summaries or presence days, newest first.

    Does not invent today's Monday when the store is empty.
    """
    rows = conn.execute(
        """SELECT day FROM daily_summaries
           UNION
           SELECT day FROM presence_days
           ORDER BY 1 DESC"""
    ).fetchall()
    mondays = []
    seen = set()
    for row in rows:
        day = agg.parse_iso_date(row["day"])
        monday = (day - timedelta(days=day.weekday())).isoformat()
        if monday not in seen:
            seen.add(monday)
            mondays.append(monday)
    return mondays


def _current_monday() -> str:
    today = datetime.now().date()
    return (today - timedelta(days=today.weekday())).isoformat()


def _week_index(conn) -> dict[str, Any]:
    today = _current_monday()
    weeks = _weeks_available(conn)
    current = weeks[0] if weeks else today
    return {
        "weeks": weeks or [today],
        "currentWeekStart": current,
        "todayWeekStart": today,
        "currentWeekHasData": bool(weeks),
    }


def _collector_gaps(conn) -> list[dict[str, Any]]:
    return [
        {"start": row["start"], "end": row["end"]}
        for row in conn.execute("SELECT start, end FROM collector_gaps")
    ]


def _monitoring_on_windows(conn, kit) -> list[tuple] | None:
    """Intervals when this kit's monitoring was on, from pull_log.

    None: no success/disabled rows (caller falls back).
    Empty list: monitoring has never been enabled.
    """
    rows = conn.execute(
        """SELECT kind, started_at, finished_at FROM pull_log
           WHERE engine = ? AND kind IN ('success', 'disabled')
           ORDER BY started_at, id""",
        (kit["engine"],),
    ).fetchall()
    if not rows:
        return None
    windows = []
    current_start = None
    saw_success = False
    for row in rows:
        when = presence_mod.parse_ts(row["started_at"])
        if row["kind"] == "success":
            saw_success = True
            if current_start is None:
                current_start = when
        elif row["kind"] == "disabled" and current_start is not None:
            windows.append((current_start, when))
            current_start = None
    if not saw_success:
        return []
    if current_start is not None:
        windows.append((current_start, None))
    return windows


def _collector_gaps_for_kit(conn, kit) -> list[dict[str, Any]]:
    """collectorGap only for sidecar outages while monitoring was on.

    A never-enabled kit (or one whose only polls are `disabled`) gets no
    collector gaps: the week stays `gapUnknown`. Periods before the first
    successful pull and periods covered by disabled polls are excluded.
    """
    gaps = _collector_gaps(conn)
    windows = _monitoring_on_windows(conn, kit)
    if windows is None:
        if _monitoring_enabled(kit) or kit["last_pulled"]:
            return gaps
        return []
    if not windows:
        return []
    return presence_mod.clip_gaps_to_windows(gaps, windows)


def _rows_in_week(conn, table: str, engine: str, start, end):
    """Fetch rows whose timestamp column falls in [start, end), offset-aware."""
    pad_lo = (start - timedelta(days=2)).date().isoformat()
    pad_hi = (end + timedelta(days=2)).date().isoformat()
    rows = conn.execute(
        "SELECT * FROM %s WHERE engine = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp"
        % table,
        (engine, pad_lo, pad_hi),
    )
    return [row for row in rows if presence_mod.in_bounds(row["timestamp"], start, end)]


def _week_bundle(conn, kit, week_start: str, now: datetime | None = None) -> dict[str, Any]:
    now = presence_mod.truncate_to_seconds(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    rows = _summaries(conn, kit["engine"], week_start)
    grouped = agg.group_by_instance(rows)
    kolibri, nextcloud, kiwix, instances = [], [], [], []
    for instance_rows in grouped.values():
        app = instance_rows[0]["app"]
        if app == "kolibri":
            item = agg.kolibri_week(instance_rows)
            kolibri.append(item)
        elif app == "nextcloud":
            item = agg.nextcloud_week(instance_rows)
            nextcloud.append(item)
        elif app == "kiwix":
            item = agg.kiwix_week(instance_rows)
            kiwix.append(item)
        else:
            item = agg.instance_envelope(instance_rows)
            item.pop("_ok_payloads", None)
            item.pop("_last_ok", None)
        instances.append(agg.discovered_instance(instance_rows))
    p_rows = conn.execute(
        """SELECT day, on_minutes, school_hours_on_minutes, boots,
                  longest_gap_minutes, length_known
           FROM presence_days WHERE engine = ? AND day >= ? AND day <= ? ORDER BY day""",
        (kit["engine"], week_start, agg.friday_of(week_start)),
    ).fetchall()
    presence_days = [
        {
            "day": r["day"],
            "onMinutes": r["on_minutes"],
            "schoolHoursOnMinutes": r["school_hours_on_minutes"],
            "boots": r["boots"],
            "longestGapMinutes": r["longest_gap_minutes"],
            "lengthKnown": bool(r["length_known"]),
        }
        for r in p_rows
    ]
    scorecard = agg.scorecard_from_weeks(kolibri, nextcloud, kiwix, presence_days, week_start)
    has_usage = bool(rows)
    stale, data_from = agg.freshness(kit["last_pulled"], now=now)
    tz = _kit_tz(conn, kit, week_start)
    segs = conn.execute(
        """SELECT state, start, end, length_known FROM presence_segments
           WHERE engine = ? ORDER BY start""",
        (kit["engine"],),
    ).fetchall()
    start, end = presence_mod.week_bounds(
        week_start, tz["utcOffset"], time_zone=tz["timeZone"] or None
    )
    raw_segments = [
        {"state": s["state"], "start": s["start"], "end": s["end"], "lengthKnown": bool(s["length_known"])}
        for s in segs
    ]
    segments = presence_mod.cover_week(raw_segments, start, end, _collector_gaps_for_kit(conn, kit), now=now)
    return {
        "kolibri": kolibri,
        "nextcloud": nextcloud,
        "kiwix": kiwix,
        "instances": instances,
        "presence_days": presence_days,
        "segments": segments,
        "scorecard": scorecard,
        "hasUsageData": has_usage,
        "stale": stale,
        "dataFrom": data_from,
        "timezone": tz,
        "headlines": agg.headlines_from(scorecard),
        "note": agg.school_note(kit["note"] or "", instances, has_usage),
        # Same own-copy set and combine rule as scorecard.setup (idea#462 item 5).
        "census": agg.school_census(kolibri),
        "presence_summary": agg.presence_summary(presence_days, week_start),
        "week_start_dt": start,
        "week_end_dt": end,
    }



def _presence_days(conn, engine: str, week_start: str) -> list[dict[str, Any]]:
    p_rows = conn.execute(
        """SELECT day, on_minutes, school_hours_on_minutes, boots,
                  longest_gap_minutes, length_known
           FROM presence_days WHERE engine = ? AND day >= ? AND day <= ? ORDER BY day""",
        (engine, week_start, agg.friday_of(week_start)),
    ).fetchall()
    return [
        {
            "day": r["day"],
            "onMinutes": r["on_minutes"],
            "schoolHoursOnMinutes": r["school_hours_on_minutes"],
            "boots": r["boots"],
            "longestGapMinutes": r["longest_gap_minutes"],
            "lengthKnown": bool(r["length_known"]),
        }
        for r in p_rows
    ]


def _scorecard_week(conn, kit, week_start: str) -> dict[str, Any]:
    rows = _summaries(conn, kit["engine"], week_start)
    grouped = agg.group_by_instance(rows)
    kolibri, nextcloud, kiwix = [], [], []
    for instance_rows in grouped.values():
        app = instance_rows[0]["app"]
        if app == "kolibri":
            kolibri.append(agg.kolibri_week(instance_rows))
        elif app == "nextcloud":
            nextcloud.append(agg.nextcloud_week(instance_rows))
        elif app == "kiwix":
            kiwix.append(agg.kiwix_week(instance_rows))
    presence_days = _presence_days(conn, kit["engine"], week_start)
    return {
        "weekStart": week_start,
        "scorecard": agg.scorecard_from_weeks(kolibri, nextcloud, kiwix, presence_days, week_start),
        "hasUsageData": bool(rows),
    }


def _weekly_scorecards(conn, kit, week_start: str, current_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    weeks = sorted(week for week in _weeks_available(conn) if week <= week_start)
    if week_start not in weeks:
        weeks.append(week_start)
    out = []
    for week in weeks:
        if week == week_start:
            out.append({
                "weekStart": week,
                "scorecard": current_bundle["scorecard"],
                "hasUsageData": current_bundle["hasUsageData"],
            })
        else:
            out.append(_scorecard_week(conn, kit, week))
    return out


def _help_events(conn, deployment_id: str, week_start: str) -> list[dict[str, Any]]:
    horizon = agg.add_days(week_start, 7)
    return [
        {"offeredOn": row["offered_on"]}
        for row in conn.execute(
            """SELECT offered_on FROM help_events
               WHERE deployment_id = ? AND offered_on < ?
               ORDER BY offered_on""",
            (deployment_id, horizon),
        )
    ]


def meta_payload(conn=None, sample_data: bool = False) -> dict[str, Any]:
    body = {
        "schema": agg.API_SCHEMA,
        "daySchema": agg.DAY_SCHEMA,
        "thresholdsConfigured": True,
        "thresholds": thresholds_mod.effective(conn),
        "staleAfterHours": int(os.environ.get("STALE_AFTER_HOURS") or agg.STALE_AFTER_HOURS),
        "hourlyChartMinWeeklyViews": int(
            os.environ.get("HOURLY_CHART_MIN_WEEKLY_VIEWS") or agg.HOURLY_CHART_MIN_WEEKLY_VIEWS
        ),
        "headerTimeZone": os.environ.get("HEADER_TIMEZONE") or agg.HEADER_TIMEZONE,
        "sampleData": sample_data,
    }
    if conn is not None:
        idx = _week_index(conn)
        body["currentWeekStart"] = idx["currentWeekStart"]
        body["todayWeekStart"] = idx["todayWeekStart"]
        body["currentWeekHasData"] = idx["currentWeekHasData"]
    else:
        today = _current_monday()
        body["currentWeekStart"] = today
        body["todayWeekStart"] = today
        body["currentWeekHasData"] = False
    return body


def handle(conn, method: str, path: str, body: dict[str, Any] | None, user: str | None, secure: bool, now: datetime | None = None):
    parsed = urlparse(path)
    route = parsed.path.rstrip("/") or "/"
    parts = [p for p in route.split("/") if p]
    now = presence_mod.truncate_to_seconds(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if method == "GET" and route == "/api/v1/health":
        return 200, {
            "ok": True,
            "schema": agg.API_SCHEMA,
            "version": buildinfo.dashboard_version(),
            "commit": buildinfo.dashboard_commit(),
        }, None

    if method == "GET" and route == "/api/v1/session":
        if user:
            return 200, {"schema": agg.API_SCHEMA, "authenticated": True, "user": {"username": user, "role": "operator"}}, None
        return 200, {"schema": agg.API_SCHEMA, "authenticated": False, "user": None}, None

    if method == "POST" and route == "/api/v1/session":
        username = (body or {}).get("username") or ""
        password = (body or {}).get("password") or ""
        if not auth.check_credentials(username, password):
            return 401, error_body("unauthorized", "Unknown operator or wrong password"), None
        token = auth.mint_token(username)
        return 200, {
            "schema": agg.API_SCHEMA,
            "authenticated": True,
            "user": {"username": username, "role": "operator"},
        }, auth.set_cookie_header(token, secure=secure)

    if method == "DELETE" and route == "/api/v1/session":
        return 200, {
            "schema": agg.API_SCHEMA,
            "authenticated": False,
            "user": None,
        }, auth.clear_cookie_header(secure=secure)

    if (method, route) not in PUBLIC_PATHS and (user is None or not auth.is_allowed(user)):
        return 401, error_body("unauthorized", "Operator session required"), None

    if method == "PUT" and route == "/api/v1/session/password":
        current = (body or {}).get("currentPassword") or ""
        new_password = (body or {}).get("newPassword") or ""
        try:
            auth.change_password(user, current, new_password)
        except auth.PasswordError as exc:
            status = 401 if exc.code == "unauthorized" else 400
            return status, error_body(exc.code, exc.message), None
        return 200, {
            "schema": agg.API_SCHEMA,
            "authenticated": True,
            "user": {"username": user, "role": "operator"},
        }, None

    if method == "GET" and route == "/api/v1/meta":
        return 200, meta_payload(conn), None

    if route == "/api/v1/settings/thresholds":
        if method == "GET":
            return 200, thresholds_mod.settings_payload(conn), None
        if method == "PUT":
            try:
                payload = thresholds_mod.apply_put(conn, body or {}, user)
            except thresholds_mod.ValidationError as exc:
                return 400, {"error": exc.error, "field": exc.field}, None
            return 200, payload, None

    if method == "GET" and route == "/api/v1/kits":
        kits = []
        for row in conn.execute("SELECT * FROM kits ORDER BY school, engine"):
            kits.append({
                "engine": row["engine"],
                "tailscaleName": row["tailscale_name"],
                "school": row["school"],
                "deploymentId": row["deployment_id"],
                "lastPulled": row["last_pulled"],
                "monitoringEnabled": _monitoring_enabled(row),
            })
        return 200, {"schema": agg.API_SCHEMA, "kits": kits}, None

    if method == "GET" and route == "/api/v1/weeks":
        idx = _week_index(conn)
        return 200, {
            "schema": agg.API_SCHEMA,
            "weeks": idx["weeks"],
            "currentWeekStart": idx["currentWeekStart"],
            "todayWeekStart": idx["todayWeekStart"],
            "currentWeekHasData": idx["currentWeekHasData"],
        }, None

    if method == "GET" and len(parts) == 4 and parts[:3] == ["api", "v1", "weeks"] and parts[3] and route.endswith("/overview"):
        # /api/v1/weeks/{weekStart}/overview — handled below via split
        pass

    # /api/v1/weeks/{weekStart}/...
    if method == "GET" and len(parts) >= 4 and parts[:3] == ["api", "v1", "weeks"]:
        week_start = parts[3]
        if not agg.is_monday(week_start):
            return 400, error_body("validation", "weekStart must be a Monday (YYYY-MM-DD)", {"weekStart": week_start}), None
        rest = parts[4:]
        meta = meta_payload(conn)
        week_end = agg.friday_of(week_start)
        if rest == ["overview"]:
            cards = []
            suggestions = []
            for kit in conn.execute("SELECT * FROM kits ORDER BY school, engine"):
                bundle = _week_bundle(conn, kit, week_start, now=now)
                card = {
                    "deploymentId": kit["deployment_id"],
                    "school": kit["school"],
                    "engine": kit["engine"],
                    "note": bundle["note"],
                    "lastPulled": kit["last_pulled"],
                    "stale": bundle["stale"],
                    "dataFrom": bundle["dataFrom"],
                    "hasUsageData": bundle["hasUsageData"],
                    "monitoringEnabled": _monitoring_enabled(kit),
                    "scorecard": bundle["scorecard"],
                    "headlines": bundle["headlines"],
                }
                cards.append(card)
                status = agg.help_status_for(
                    card,
                    kit,
                    bundle["scorecard"],
                    bundle["presence_days"],
                    thresholds=meta["thresholds"],
                    weekly=_weekly_scorecards(conn, kit, week_start, bundle),
                    help_events=_help_events(conn, kit["deployment_id"], week_start),
                    week_start=week_start,
                )
                card["unused"] = bool(status["unused"])
                if status["suggestion"]:
                    suggestions.append(status["suggestion"])
            return 200, {
                "schema": agg.API_SCHEMA,
                "weekStart": week_start,
                "weekEnd": week_end,
                "weekLabel": agg.format_week_label(week_start, week_end),
                "thresholdsConfigured": meta["thresholdsConfigured"],
                "sampleData": meta["sampleData"],
                "staleAfterHours": meta["staleAfterHours"],
                "cards": cards,
                "helpSuggestions": suggestions,
            }, None

        if len(rest) >= 2 and rest[0] == "schools":
            deployment_id = rest[1]
            kit = db.kit_by_deployment(conn, deployment_id)
            if kit is None:
                return 404, error_body("not_found", "Unknown deployment", {"deploymentId": deployment_id}), None
            bundle = _week_bundle(conn, kit, week_start, now=now)
            tail = rest[2:]
            if not tail:
                status = agg.help_status_for(
                    {"hasUsageData": bundle["hasUsageData"]},
                    kit,
                    bundle["scorecard"],
                    bundle["presence_days"],
                    thresholds=meta["thresholds"],
                    weekly=_weekly_scorecards(conn, kit, week_start, bundle),
                    help_events=_help_events(conn, kit["deployment_id"], week_start),
                    week_start=week_start,
                )
                return 200, {
                    "schema": agg.API_SCHEMA,
                    "weekStart": week_start,
                    "weekEnd": week_end,
                    "deploymentId": deployment_id,
                    "school": kit["school"],
                    "engine": kit["engine"],
                    "lastPulled": kit["last_pulled"],
                    "stale": bundle["stale"],
                    "dataFrom": bundle["dataFrom"],
                    "hasUsageData": bundle["hasUsageData"],
                    "monitoringEnabled": _monitoring_enabled(kit),
                    "thresholdsConfigured": meta["thresholdsConfigured"],
                    "sampleData": meta["sampleData"],
                    "timezone": bundle["timezone"],
                    "scorecard": bundle["scorecard"],
                    "census": bundle["census"],
                    "presence": {
                        "timezone": bundle["timezone"],
                        "segments": bundle["segments"],
                        "summary": bundle["presence_summary"],
                    },
                    "clockTrusted": agg.clocks_trusted(bundle["instances"]),
                    "unused": bool(status["unused"]),
                }, None
            if tail == ["presence"]:
                return 200, {
                    "schema": agg.API_SCHEMA,
                    "deploymentId": deployment_id,
                    "weekStart": week_start,
                    "timezone": bundle["timezone"],
                    "segments": bundle["segments"],
                    "days": bundle["presence_days"],
                }, None
            if tail == ["uplink"]:
                week_lo, week_hi = bundle["week_start_dt"], bundle["week_end_dt"]
                samples = [
                    {
                        "timestamp": r["timestamp"],
                        "engine": r["engine"],
                        "online": bool(r["online"]),
                        "lastSeen": r["last_seen"],
                        "via": r["via"],
                        "latencyMs": r["latency_ms"],
                    }
                    for r in _rows_in_week(conn, "uplink_samples", kit["engine"], week_lo, week_hi)
                ]
                transitions = [
                    {
                        "timestamp": r["timestamp"],
                        "engine": r["engine"],
                        "fromState": r["from_state"],
                        "toState": r["to_state"],
                    }
                    for r in _rows_in_week(conn, "uplink_transitions", kit["engine"], week_lo, week_hi)
                ]
                return 200, {
                    "schema": agg.API_SCHEMA,
                    "deploymentId": deployment_id,
                    "weekStart": week_start,
                    "timezone": bundle["timezone"],
                    "measured": bool(samples),
                    "samples": samples,
                    "transitions": transitions,
                }, None
            if tail == ["kolibri"]:
                return 200, {
                    "schema": agg.API_SCHEMA,
                    "deploymentId": deployment_id,
                    "weekStart": week_start,
                    "clockTrusted": agg.clocks_trusted(bundle["kolibri"]),
                    "instances": bundle["kolibri"],
                }, None
            if tail == ["nextcloud"]:
                return 200, {
                    "schema": agg.API_SCHEMA,
                    "deploymentId": deployment_id,
                    "weekStart": week_start,
                    "clockTrusted": agg.clocks_trusted(bundle["nextcloud"]),
                    "instances": bundle["nextcloud"],
                }, None
            if tail == ["kiwix"]:
                return 200, {
                    "schema": agg.API_SCHEMA,
                    "deploymentId": deployment_id,
                    "weekStart": week_start,
                    "clockTrusted": agg.clocks_trusted(bundle["kiwix"]),
                    "instances": bundle["kiwix"],
                }, None
            if tail == ["instances"]:
                return 200, {"schema": agg.API_SCHEMA, "deploymentId": deployment_id, "weekStart": week_start, "instances": bundle["instances"]}, None

    if len(parts) == 5 and parts[:3] == ["api", "v1", "schools"] and parts[4] == "help-events":
        deployment_id = parts[3]
        kit = db.kit_by_deployment(conn, deployment_id)
        if kit is None:
            return 404, error_body("not_found", "Unknown deployment", {"deploymentId": deployment_id}), None
        if method == "GET":
            events = []
            for row in conn.execute(
                "SELECT * FROM help_events WHERE deployment_id = ? ORDER BY offered_on, created_at",
                (deployment_id,),
            ):
                events.append({
                    "id": row["id"],
                    "deploymentId": row["deployment_id"],
                    "offeredOn": row["offered_on"],
                    "tutorialChapters": json.loads(row["tutorial_chapters"]),
                    "note": row["note"],
                    "createdBy": row["created_by"],
                    "createdAt": row["created_at"],
                })
            trend = []
            for week_start in _weeks_available(conn):
                bundle = _week_bundle(conn, kit, week_start, now=now)
                trend.append({"weekStart": week_start, "scorecard": bundle["scorecard"]})
            return 200, {
                "schema": agg.API_SCHEMA,
                "deploymentId": deployment_id,
                "events": events,
                "weeklyTrend": trend,
            }, None
        if method == "POST":
            offered = (body or {}).get("offeredOn") or ""
            chapters = (body or {}).get("tutorialChapters")
            note = (body or {}).get("note") or ""
            if not offered or len(offered) != 10:
                return 400, error_body("validation", "offeredOn must be YYYY-MM-DD"), None
            try:
                agg.parse_iso_date(offered)
            except ValueError:
                return 400, error_body("validation", "offeredOn must be YYYY-MM-DD"), None
            if not isinstance(chapters, list) or not all(isinstance(c, str) for c in chapters):
                return 400, error_body("validation", "tutorialChapters must be an array of strings"), None
            import uuid
            created = db.now_rfc3339()
            event_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO help_events(id, deployment_id, offered_on, tutorial_chapters, note, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event_id, deployment_id, offered, json.dumps(chapters), note, user or "", created),
            )
            conn.commit()
            return 201, {
                "id": event_id,
                "deploymentId": deployment_id,
                "offeredOn": offered,
                "tutorialChapters": chapters,
                "note": note,
                "createdBy": user or "",
                "createdAt": created,
            }, None

    return 404, error_body("not_found", "No such endpoint"), None


class Handler(BaseHTTPRequestHandler):
    conn = None

    def log_message(self, fmt, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send(self, status: int, payload: dict[str, Any], set_cookie: str | None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method: str):
        secure = (self.headers.get("X-Forwarded-Proto") == "https") or (self.command == "https")
        token = auth.cookie_from_header(self.headers.get("Cookie"))
        user = auth.read_token(token)
        try:
            body = self._read_json() if method in ("POST", "PUT", "PATCH") else None
        except json.JSONDecodeError:
            self._send(400, error_body("validation", "Request body is not JSON"), None)
            return
        try:
            status, payload, cookie = handle(self.conn, method, self.path, body, user, secure)
        except Exception as exc:  # noqa: BLE001 — last-resort envelope
            status, payload, cookie = 500, error_body("unavailable", "Internal error"), None
            # Keep the reason out of the client body; it still lands in stderr for operators.
            sys_stderr = __import__("sys").stderr
            print("api error: %s" % exc, file=sys_stderr)
        self._send(status, payload, cookie)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_PUT(self):
        self._dispatch("PUT")


def serve(conn, bind: str = "0.0.0.0:8080"):
    host, port_s = bind.rsplit(":", 1)
    Handler.conn = conn
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((host, int(port_s)), Handler)
    return server
