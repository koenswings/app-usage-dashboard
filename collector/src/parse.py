"""Parse the idea-usage-export NDJSON stream (agent-engine-dev#308 §7)."""
from __future__ import annotations

import json
from typing import Any


class DisabledExport(Exception):
    """Exit 10: usageMonitoring is off. This is a state, not an error."""


class InvalidExport(Exception):
    """Partial, invalid or unexpected export output. Keep the last good copy."""


RECORD_TYPES = ("presence", "day", "sample")


def parse_since_stream(text: str) -> dict[str, Any]:
    if text is None:
        raise InvalidExport("empty stream")
    presence: list[dict[str, Any]] = []
    days: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    end = None
    buckets = {"presence": presence, "day": days, "sample": samples}
    saw_line = False
    for index, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        saw_line = True
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InvalidExport("invalid JSON on line %s" % index) from exc
        if not isinstance(obj, dict):
            raise InvalidExport("line %s is not an object" % index)
        kind = obj.get("type")
        if kind == "end":
            end = obj
        elif kind in buckets:
            buckets[kind].append(obj)
        # unknown types are ignored (forward compatible)
    if not saw_line:
        raise InvalidExport("empty stream")
    if end is None:
        raise InvalidExport("missing end marker")
    return {"presence": presence, "days": days, "samples": samples, "end": end}


def interpret_export(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    err = (stderr or "").strip()
    out = stdout or ""
    if returncode == 10:
        if out.strip():
            raise InvalidExport("exit 10 but stdout was not empty")
        if err and err.splitlines()[0].strip() != "disabled":
            raise InvalidExport("exit 10 with unexpected stderr: %s" % err)
        raise DisabledExport("disabled")
    if returncode == 2:
        raise InvalidExport(err or "invalid arguments")
    if returncode != 0:
        raise InvalidExport("export failed (%s): %s" % (returncode, err))
    return parse_since_stream(out)
