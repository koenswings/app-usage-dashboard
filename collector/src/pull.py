"""SSH pull of idea-usage-export (since / archive-and-clear) via the sidecar SOCKS5."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, timedelta
from typing import Any

from . import db
from .parse import DisabledExport, InvalidExport, interpret_export
from . import presence as presence_mod


def known_hosts_path() -> str:
    override = os.environ.get("IDEA_USAGE_KNOWN_HOSTS")
    if override:
        return override
    data_dir = os.environ.get("DATA_DIR") or "/data"
    return os.path.join(data_dir, "known_hosts")


def ssh_base(host: str, key: str, socks: str | None = None, port: int = 22) -> list[str]:
    cmd = [
        os.environ.get("IDEA_USAGE_SSH") or "ssh",
        "-i", key,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "LogLevel=ERROR",
        "-o", "UserKnownHostsFile=%s" % known_hosts_path(),
        "-p", str(port),
    ]
    if socks:
        cmd.extend(["-o", "ProxyCommand=nc -x %s %%h %%p" % socks])
    cmd.append("pi@%s" % host)
    return cmd


def run_export(host: str, key: str, args: list[str], socks: str | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = ssh_base(host, key, socks=socks) + args
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, text=True
    )


def store_export(conn, engine: str, parsed: dict[str, Any], pulled_at: str, deployment_id: str) -> None:
    for rec in parsed.get("presence") or []:
        payload = rec.get("payload") or {}
        ts = payload.get("ts")
        if not ts:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO presence_samples
               (engine, day, ts, payload, boot_id, uptime_s, ntp_synced)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                engine,
                rec.get("day") or payload.get("day") or (ts[:10] if ts else ""),
                ts,
                json.dumps(payload),
                payload.get("bootId"),
                payload.get("uptimeS"),
                1 if payload.get("ntpSynced") else 0,
            ),
        )
    for rec in parsed.get("days") or []:
        payload = rec.get("payload") or {}
        instance = payload.get("instance") or rec.get("instance")
        day = payload.get("day") or rec.get("day")
        if not instance or not day:
            continue
        conn.execute(
            """INSERT OR REPLACE INTO daily_summaries
               (engine, deployment_id, day, instance, app, name, demo, listed,
                hook_status, skip_reason, payload, pulled_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                engine,
                deployment_id,
                day,
                instance,
                payload.get("app") or rec.get("app") or "",
                payload.get("name"),
                1 if payload.get("demo") else 0,
                None if payload.get("listed") is None else (1 if payload.get("listed") else 0),
                payload.get("hookStatus"),
                payload.get("skipReason"),
                json.dumps(payload),
                pulled_at,
            ),
        )
    for rec in parsed.get("samples") or []:
        payload = rec.get("payload") or {}
        conn.execute(
            """INSERT INTO samples (engine, day, instance, sampled_at, payload, pulled_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                engine,
                rec.get("day") or payload.get("day") or "",
                rec.get("instance") or payload.get("instance") or "",
                payload.get("sampledAt"),
                json.dumps(payload),
                pulled_at,
            ),
        )
    rebuild_presence(conn, engine)
    conn.execute(
        "UPDATE kits SET last_pulled = ?, monitoring_enabled = 1 WHERE engine = ?",
        (pulled_at, engine),
    )


def rebuild_presence(conn, engine: str) -> None:
    rows = conn.execute(
        "SELECT payload FROM presence_samples WHERE engine = ? ORDER BY ts",
        (engine,),
    ).fetchall()
    samples = [json.loads(row["payload"]) for row in rows]
    segments = presence_mod.derive_segments(samples)
    gaps = conn.execute(
        "SELECT start, end, reason FROM collector_gaps"
    ).fetchall()
    gap_list = [{"start": g["start"], "end": g["end"], "reason": g["reason"]} for g in gaps]
    segments = presence_mod.overlay_collector_gaps(segments, gap_list)
    conn.execute("DELETE FROM presence_segments WHERE engine = ?", (engine,))
    for seg in segments:
        conn.execute(
            """INSERT INTO presence_segments(engine, state, start, end, length_known)
               VALUES (?, ?, ?, ?, ?)""",
            (engine, seg["state"], seg["start"], seg["end"], 1 if seg["lengthKnown"] else 0),
        )
    # Day roll-ups from the derived segments.
    days = set()
    for seg in segments:
        days.add(seg["start"][:10])
        days.add(seg["end"][:10])
    kit = db.kit_by_engine(conn, engine)
    offset = None
    if samples:
        offset = samples[-1].get("ts")
        offset = offset[-6:] if offset and len(offset) >= 6 and offset[-6] in "+-" else None
    tzinfo = presence_mod.parse_ts(samples[-1]["ts"]).tzinfo if samples else None
    conn.execute("DELETE FROM presence_days WHERE engine = ?", (engine,))
    boot_starts: dict[str, set[str]] = {}
    for sample in samples:
        ts = sample.get("ts")
        uptime = int(sample.get("uptimeS") or 0)
        boot = sample.get("bootId") or ""
        if not (ts and boot and sample.get("ntpSynced")):
            continue
        start = presence_mod.parse_ts(ts) - __import__("datetime").timedelta(seconds=max(uptime, 0))
        boot_starts.setdefault(start.date().isoformat(), set()).add(boot)
    for day in sorted(days):
        if len(day) != 10:
            continue
        roll = presence_mod.rollup_day(segments, day, tzinfo)
        conn.execute(
            """INSERT OR REPLACE INTO presence_days
               (engine, day, on_minutes, school_hours_on_minutes, boots,
                longest_gap_minutes, length_known)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                engine, day, roll["onMinutes"], roll["schoolHoursOnMinutes"],
                len(boot_starts.get(day, ())),
                roll["longestGapMinutes"],
                1 if roll["lengthKnown"] else 0,
            ),
        )


def record_pull_log(conn, engine: str, started_at: str, ok: bool, kind: str, since_day: str | None, message: str, counts=None):
    conn.execute(
        """INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, since_day, message, counts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            engine, started_at, db.now_rfc3339(), 1 if ok else 0, kind, since_day, message,
            json.dumps(counts) if counts is not None else None,
        ),
    )


def handle_pull(conn, engine: str, host: str, key: str, since_day: str, socks: str | None = None) -> str:
    started = db.now_rfc3339()
    kit = db.kit_by_engine(conn, engine)
    deployment_id = kit["deployment_id"] if kit else engine
    try:
        proc = run_export(host, key, ["since", since_day], socks=socks)
        parsed = interpret_export(proc.returncode, proc.stdout, proc.stderr)
    except DisabledExport:
        conn.execute("UPDATE kits SET monitoring_enabled = 0 WHERE engine = ?", (engine,))
        record_pull_log(conn, engine, started, True, "disabled", since_day, "disabled")
        conn.commit()
        return "disabled"
    except InvalidExport as exc:
        record_pull_log(conn, engine, started, False, "rejected", since_day, str(exc))
        conn.commit()
        return "rejected"
    except (subprocess.TimeoutExpired, OSError) as exc:
        record_pull_log(conn, engine, started, False, "error", since_day, str(exc))
        conn.commit()
        return "error"
    pulled_at = db.now_rfc3339()
    store_export(conn, engine, parsed, pulled_at, deployment_id)
    end = parsed.get("end") or {}
    record_pull_log(conn, engine, started, True, "success", since_day, "ok", end.get("counts"))
    # After a confirmed copy, clear kit-local days strictly before (today - 14).
    before = (date.today() - timedelta(days=14)).isoformat()
    try:
        proc = run_export(host, key, ["archive-and-clear", "--before", before], socks=socks)
        if proc.returncode == 10:
            pass
        elif proc.returncode != 0:
            record_pull_log(conn, engine, pulled_at, False, "archive-error", before, proc.stderr)
    except (subprocess.TimeoutExpired, OSError) as exc:
        record_pull_log(conn, engine, pulled_at, False, "archive-error", before, str(exc))
    conn.commit()
    return "success"


def record_uplink(conn, engine: str, timestamp: str, online: bool, last_seen: str | None, via: str | None, latency_ms):
    last = conn.execute(
        "SELECT online FROM uplink_samples WHERE engine = ? ORDER BY timestamp DESC LIMIT 1",
        (engine,),
    ).fetchone()
    conn.execute(
        """INSERT OR IGNORE INTO uplink_samples(engine, timestamp, online, last_seen, via, latency_ms)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (engine, timestamp, 1 if online else 0, last_seen, via, latency_ms),
    )
    if last is not None and bool(last["online"]) != bool(online):
        conn.execute(
            """INSERT INTO uplink_transitions(engine, timestamp, from_state, to_state)
               VALUES (?, ?, ?, ?)""",
            (engine, timestamp, "online" if last["online"] else "offline", "online" if online else "offline"),
        )
        return "online" if online else "offline"
    return None
