#!/usr/bin/env python3
"""Ingest an idea-usage-export NDJSON stream into a dashboard SQLite store.

This is the host-side path used when the collector cannot pull from its own
kit (docs/runbook.md, test-host self-pull limit): parse_since_stream /
interpret_export + store_export. It never writes /var/lib/idea/usage and
never runs archive-and-clear.

Usage:
  script/ingest-usage-export.py --db <usage.sqlite> --engine idea03 \\
      --deployment-id dep-idea03-tar-e2e --stream <export.ndjson> \\
      [--registry <registry.json>] [--pulled-at RFC3339]

The process does not print credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collector"))

from src import db  # noqa: E402
from src.parse import interpret_export  # noqa: E402
from src.pull import store_export  # noqa: E402


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to usage.sqlite")
    parser.add_argument("--engine", required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--stream", required=True, help="NDJSON from idea-usage-export")
    parser.add_argument("--registry", help="optional registry.json to upsert kits")
    parser.add_argument("--pulled-at", default="")
    parser.add_argument("--returncode", type=int, default=0)
    parser.add_argument("--stderr", default="")
    args = parser.parse_args()

    stream_path = Path(args.stream)
    text = stream_path.read_text(encoding="utf-8")
    parsed = interpret_export(args.returncode, text, args.stderr)
    days = sorted({r.get("day") or (r.get("payload") or {}).get("day") for r in parsed.get("days") or []} - {None, ""})
    presence_days = sorted({r.get("day") or (r.get("payload") or {}).get("day") for r in parsed.get("presence") or []} - {None, ""})
    counts = {
        "day": len(parsed.get("days") or []),
        "presence": len(parsed.get("presence") or []),
        "sample": len(parsed.get("samples") or []),
    }

    conn = db.connect(args.db)
    if args.registry:
        db.load_registry(conn, args.registry)
    kit = db.kit_by_engine(conn, args.engine)
    if kit is None:
        raise SystemExit("ERROR: kit %s is not in the store (pass --registry)" % args.engine)

    pulled_at = args.pulled_at or now_rfc3339()
    store_export(conn, args.engine, parsed, pulled_at, args.deployment_id)
    conn.commit()
    summary = {
        "ok": True,
        "engine": args.engine,
        "deploymentId": args.deployment_id,
        "pulledAt": pulled_at,
        "counts": counts,
        "dayDates": days,
        "presenceDates": presence_days,
        "end": parsed.get("end") or {},
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
