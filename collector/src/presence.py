"""Derive presence segments from kit samples plus idea-side collector gaps."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

SCHOOL_HOUR_START = 7
SCHOOL_HOUR_END = 16


def parse_ts(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def rfc3339(dt: datetime, tz=None) -> str:
    if tz is not None:
        dt = dt.astimezone(tz)
    return dt.isoformat(timespec="seconds")


def normalize_offset(offset: str | None) -> str:
    raw = (offset or "+00:00").strip() or "+00:00"
    if raw in ("Z", "z"):
        return "+00:00"
    return raw


def week_bounds(week_start: str, utc_offset: str | None, week_end: str | None = None) -> tuple[datetime, datetime]:
    """Monday 00:00 to Saturday 00:00 (end of Friday) in kit-local offset.

    Matches Pixel's PresenceStrip: origin = weekStartT00:00:00offset,
    end = (weekEnd+1)T00:00:00offset, where weekEnd is Friday.
    """
    offset = normalize_offset(utc_offset)
    if week_end is None:
        week_end = (date.fromisoformat(week_start) + timedelta(days=4)).isoformat()
    start = parse_ts("%sT00:00:00%s" % (week_start, offset))
    end_day = (date.fromisoformat(week_end) + timedelta(days=1)).isoformat()
    end = parse_ts("%sT00:00:00%s" % (end_day, offset))
    return start, end


def in_bounds(ts: str | datetime, start: datetime, end: datetime) -> bool:
    when = parse_ts(ts) if isinstance(ts, str) else ts
    return start <= when < end


def _payload(row: Any) -> dict[str, Any]:
    if isinstance(row, dict) and "payload" in row and isinstance(row["payload"], dict):
        return row["payload"]
    if isinstance(row, dict) and "payload" in row and isinstance(row["payload"], str):
        return json.loads(row["payload"])
    return row if isinstance(row, dict) else {}


def derive_segments(samples: list[Any]) -> list[dict[str, Any]]:
    """Walk kit presence samples (idea-usage-presence/1) into on/off/gapUnknown."""
    parsed: list[dict[str, Any]] = []
    for raw in samples:
        body = _payload(raw)
        ts = body.get("ts")
        if not ts:
            continue
        parsed.append(
            {
                "ts": parse_ts(ts),
                "ts_raw": ts,
                "boot": body.get("bootId") or "",
                "uptime": int(body.get("uptimeS") or 0),
                "synced": bool(body.get("ntpSynced")),
            }
        )
    parsed.sort(key=lambda item: item["ts"])
    if not parsed:
        return []

    segments: list[dict[str, Any]] = []
    on_start = parsed[0]["ts"]
    prev = parsed[0]

    def close_on(end: datetime, known: bool = True) -> None:
        if end < on_start:
            return
        segments.append(
            {"state": "on", "start": rfc3339(on_start), "end": rfc3339(end), "lengthKnown": known}
        )

    for cur in parsed[1:]:
        same_boot = cur["boot"] and cur["boot"] == prev["boot"] and cur["uptime"] >= prev["uptime"]
        if same_boot:
            prev = cur
            continue
        close_on(prev["ts"], known=True)
        # Gap between the previous sample and this new boot.
        if prev["synced"] and cur["synced"]:
            boot_start = cur["ts"] - timedelta(seconds=max(cur["uptime"], 0))
            gap_end = boot_start if boot_start > prev["ts"] else cur["ts"]
            if gap_end > prev["ts"]:
                segments.append(
                    {
                        "state": "off",
                        "start": rfc3339(prev["ts"]),
                        "end": rfc3339(gap_end),
                        "lengthKnown": True,
                    }
                )
            on_start = gap_end if gap_end <= cur["ts"] else cur["ts"]
        else:
            segments.append(
                {
                    "state": "gapUnknown",
                    "start": rfc3339(prev["ts"]),
                    "end": rfc3339(cur["ts"]),
                    "lengthKnown": False,
                }
            )
            on_start = cur["ts"]
        prev = cur
    close_on(prev["ts"], known=True)
    return _merge_adjacent(segments)


def overlay_collector_gaps(
    segments: list[dict[str, Any]], gaps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Punch collectorGap through holes (gapUnknown or missing), never through observed on/off."""
    if not gaps:
        return segments
    out = list(segments)
    extras: list[dict[str, Any]] = []
    for gap in gaps:
        g0 = parse_ts(gap["start"])
        g1 = parse_ts(gap["end"] or gap["start"])
        covered = False
        for seg in segments:
            if seg["state"] in ("on", "off"):
                s0, s1 = parse_ts(seg["start"]), parse_ts(seg["end"])
                if s0 < g1 and s1 > g0:
                    covered = True
                    break
        # Always record the idea-side outage as its own segment when it
        # does not sit entirely inside observed on/off (those stay as-is).
        if not covered:
            extras.append(
                {
                    "state": "collectorGap",
                    "start": rfc3339(g0),
                    "end": rfc3339(g1),
                    "lengthKnown": False,
                }
            )
        else:
            # Still show the collector gap: split any overlapping gapUnknown,
            # and insert the collectorGap so the strip can draw it. Observed
            # on/off remain; the extra segment sits alongside for the API
            # (Pixel draws mutually exclusive segments — prefer inserting
            # collectorGap only where we would otherwise show gapUnknown).
            replaced: list[dict[str, Any]] = []
            for seg in out:
                if seg["state"] != "gapUnknown":
                    replaced.append(seg)
                    continue
                s0, s1 = parse_ts(seg["start"]), parse_ts(seg["end"])
                if s1 <= g0 or s0 >= g1:
                    replaced.append(seg)
                    continue
                if s0 < g0:
                    replaced.append(
                        {**seg, "end": rfc3339(g0)}
                    )
                replaced.append(
                    {
                        "state": "collectorGap",
                        "start": rfc3339(max(s0, g0)),
                        "end": rfc3339(min(s1, g1)),
                        "lengthKnown": False,
                    }
                )
                if s1 > g1:
                    replaced.append({**seg, "start": rfc3339(g1)})
            out = replaced
    return _merge_adjacent(out + extras)


def _merge_adjacent(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: (item["start"], item["state"]))
    merged = [dict(ordered[0])]
    for seg in ordered[1:]:
        prev = merged[-1]
        if (
            prev["state"] == seg["state"]
            and prev["lengthKnown"] == seg["lengthKnown"]
            and prev["end"] >= seg["start"]
        ):
            if seg["end"] > prev["end"]:
                prev["end"] = seg["end"]
        else:
            merged.append(dict(seg))
    return merged


def cover_week(
    segments: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    collector_gaps: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Partition [start, end) into contiguous, non-overlapping segments.

    Observed `on` / `off` from the kit export win over idea-side gaps.
    Unmeasured stretches become `collectorGap` where a watchdog /
    collector_gaps interval (or an already-stored collectorGap) covers
    them, and `gapUnknown` otherwise. The pieces sum to (end - start).
    """
    if end <= start:
        return []
    tz = start.tzinfo
    now = now or datetime.now(timezone.utc)
    observed: list[dict[str, Any]] = []

    def _add(state: str, s0: datetime, s1: datetime, known: bool, priority: int) -> None:
        a, b = max(s0, start), min(s1, end)
        if b > a:
            observed.append({
                "state": state,
                "start": a,
                "end": b,
                "lengthKnown": bool(known),
                "priority": priority,
            })

    for seg in segments:
        state = seg.get("state") or "gapUnknown"
        if state == "on" or state == "off":
            priority = 0
        elif state == "collectorGap":
            priority = 1
        else:
            priority = 2
        _add(state, parse_ts(seg["start"]), parse_ts(seg["end"]), bool(seg.get("lengthKnown", True)), priority)

    for gap in collector_gaps or []:
        g0 = parse_ts(gap["start"])
        raw_end = gap.get("end")
        if raw_end:
            g1, known = parse_ts(raw_end), True
        else:
            g1, known = now, False
        _add("collectorGap", g0, g1, known, 1)

    points = {start, end}
    for item in observed:
        points.add(item["start"])
        points.add(item["end"])
    ordered = sorted(points)
    pieces: list[dict[str, Any]] = []
    for i in range(len(ordered) - 1):
        a, b = ordered[i], ordered[i + 1]
        if b <= a:
            continue
        covering = [item for item in observed if item["start"] <= a and item["end"] >= b]
        if covering:
            covering.sort(key=lambda item: (item["priority"], 0 if item["lengthKnown"] else 1))
            winner = covering[0]
            pieces.append({
                "state": winner["state"],
                "start": rfc3339(a, tz),
                "end": rfc3339(b, tz),
                "lengthKnown": winner["lengthKnown"],
            })
        else:
            pieces.append({
                "state": "gapUnknown",
                "start": rfc3339(a, tz),
                "end": rfc3339(b, tz),
                "lengthKnown": False,
            })
    return _merge_adjacent(pieces)


def clip_segments(
    segments: list[dict[str, Any]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    out = []
    for seg in segments:
        s0, s1 = parse_ts(seg["start"]), parse_ts(seg["end"])
        a, b = max(s0, start), min(s1, end)
        if b > a:
            out.append({**seg, "start": rfc3339(a), "end": rfc3339(b)})
    return out


def rollup_day(
    segments: list[dict[str, Any]],
    day: str,
    tzinfo,
    school_start: int = SCHOOL_HOUR_START,
    school_end: int = SCHOOL_HOUR_END,
) -> dict[str, Any]:
    """Presence_days row for one kit-local calendar date."""
    start = datetime.fromisoformat("%sT00:00:00" % day).replace(tzinfo=tzinfo)
    end = start + timedelta(days=1)
    clipped = clip_segments(segments, start, end)
    on_minutes = 0
    school_minutes = 0
    longest_gap = 0
    length_known = True
    for seg in clipped:
        s0, s1 = parse_ts(seg["start"]), parse_ts(seg["end"])
        minutes = int((s1 - s0).total_seconds() // 60)
        if seg["state"] == "on":
            on_minutes += minutes
            window0 = start.replace(hour=school_start, minute=0, second=0, microsecond=0)
            window1 = start.replace(hour=school_end, minute=0, second=0, microsecond=0)
            a, b = max(s0, window0), min(s1, window1)
            if b > a:
                school_minutes += int((b - a).total_seconds() // 60)
        elif seg["state"] in ("off", "gapUnknown", "collectorGap"):
            longest_gap = max(longest_gap, minutes)
            if not seg.get("lengthKnown", True):
                length_known = False
    return {
        "day": day,
        "onMinutes": on_minutes,
        "schoolHoursOnMinutes": school_minutes,
        "longestGapMinutes": longest_gap,
        "lengthKnown": length_known,
    }
