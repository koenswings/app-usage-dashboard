"""SQLite WAL store for the idea-hosted usage collector (proposal §7.5)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

SCHEMA_VERSION = 1
SNAPSHOT_KEEP = 14
# One consistent copy per UTC day: ./data/backup/usage-YYYY-MM-DD.sqlite
SNAPSHOT_NAME_RE = re.compile(r"^usage-([0-9]{4}-[0-9]{2}-[0-9]{2})\.sqlite$")

DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kits (
  engine TEXT PRIMARY KEY,
  tailscale_name TEXT NOT NULL,
  school TEXT NOT NULL,
  deployment_id TEXT NOT NULL,
  timezone TEXT,
  monitoring_enabled INTEGER,
  last_pulled TEXT,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS uplink_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  engine TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  online INTEGER NOT NULL,
  last_seen TEXT,
  via TEXT,
  latency_ms REAL,
  UNIQUE(engine, timestamp)
);

CREATE TABLE IF NOT EXISTS uplink_transitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  engine TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  from_state TEXT NOT NULL,
  to_state TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS presence_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  engine TEXT NOT NULL,
  day TEXT NOT NULL,
  ts TEXT NOT NULL,
  payload TEXT NOT NULL,
  boot_id TEXT,
  uptime_s INTEGER,
  ntp_synced INTEGER,
  UNIQUE(engine, ts)
);

CREATE TABLE IF NOT EXISTS presence_segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  engine TEXT NOT NULL,
  state TEXT NOT NULL,
  start TEXT NOT NULL,
  end TEXT NOT NULL,
  length_known INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS presence_days (
  engine TEXT NOT NULL,
  day TEXT NOT NULL,
  on_minutes INTEGER,
  school_hours_on_minutes INTEGER,
  boots INTEGER,
  longest_gap_minutes INTEGER,
  length_known INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (engine, day)
);

CREATE TABLE IF NOT EXISTS daily_summaries (
  engine TEXT NOT NULL,
  deployment_id TEXT NOT NULL,
  day TEXT NOT NULL,
  instance TEXT NOT NULL,
  app TEXT NOT NULL,
  name TEXT,
  demo INTEGER NOT NULL DEFAULT 0,
  listed INTEGER,
  hook_status TEXT,
  skip_reason TEXT,
  payload TEXT NOT NULL,
  pulled_at TEXT NOT NULL,
  PRIMARY KEY (engine, day, instance)
);

CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  engine TEXT NOT NULL,
  day TEXT NOT NULL,
  instance TEXT NOT NULL,
  sampled_at TEXT,
  payload TEXT NOT NULL,
  pulled_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS help_events (
  id TEXT PRIMARY KEY,
  deployment_id TEXT NOT NULL,
  offered_on TEXT NOT NULL,
  tutorial_chapters TEXT NOT NULL,
  note TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pull_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  engine TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER NOT NULL,
  kind TEXT NOT NULL,
  since_day TEXT,
  message TEXT,
  counts TEXT
);

CREATE TABLE IF NOT EXISTS collector_gaps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  start TEXT NOT NULL,
  end TEXT,
  reason TEXT
);
"""


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(DDL)
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.commit()
    return conn


def vacuum_into(conn: sqlite3.Connection, dest: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    conn.execute("VACUUM INTO ?", (dest,))


def utc_day(now: datetime | None = None) -> str:
    """Calendar day in UTC, used as the snapshot's once-per-day key and filename."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.date().isoformat()


def is_snapshot_name(name: str) -> bool:
    return SNAPSHOT_NAME_RE.match(name) is not None


def snapshot_path(backup_dir: str, day: str) -> str:
    return os.path.join(backup_dir, f"usage-{day}.sqlite")


def list_snapshot_files(backup_dir: str) -> list[tuple[str, str]]:
    """(utc_day, path) for usage-YYYY-MM-DD.sqlite files, newest day first."""
    if not os.path.isdir(backup_dir):
        return []
    found: list[tuple[str, str]] = []
    for name in os.listdir(backup_dir):
        m = SNAPSHOT_NAME_RE.match(name)
        if not m:
            continue
        found.append((m.group(1), os.path.join(backup_dir, name)))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def prune_backups(backup_dir: str, keep: int = SNAPSHOT_KEEP) -> list[str]:
    """Delete older usage-YYYY-MM-DD.sqlite files only. Other files are left alone."""
    if not os.path.isdir(backup_dir):
        return []
    removed: list[str] = []
    for _day, path in list_snapshot_files(backup_dir)[keep:]:
        try:
            os.remove(path)
            removed.append(path)
        except OSError:
            pass
    return removed


def take_daily_snapshot(
    conn: sqlite3.Connection,
    backup_dir: str,
    now: datetime | None = None,
    keep: int = SNAPSHOT_KEEP,
    vacuum=None,
) -> str | None:
    """Write today's UTC snapshot if that file does not already exist.

    Uses VACUUM INTO a temp file in backup_dir, then os.replace onto
    usage-YYYY-MM-DD.sqlite. Returns the new path, or None if the day's
    file was already present (restart-safe). Raises on failure.
    """
    day = utc_day(now)
    os.makedirs(backup_dir, exist_ok=True)
    dest = snapshot_path(backup_dir, day)
    if os.path.exists(dest):
        return None
    fd, tmp = tempfile.mkstemp(prefix=f"usage-{day}.", suffix=".tmp", dir=backup_dir)
    os.close(fd)
    os.unlink(tmp)
    try:
        (vacuum or vacuum_into)(conn, tmp)
        os.replace(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
    prune_backups(backup_dir, keep=keep)
    return dest


def maybe_daily_snapshot(
    conn: sqlite3.Connection,
    backup_dir: str,
    now: datetime | None = None,
    keep: int = SNAPSHOT_KEEP,
    vacuum=None,
) -> str | None:
    """take_daily_snapshot, but log failures to stderr and never raise."""
    try:
        path = take_daily_snapshot(conn, backup_dir, now=now, keep=keep, vacuum=vacuum)
        if path:
            print("collector: wrote daily snapshot %s" % path, file=sys.stderr, flush=True)
        return path
    except Exception as exc:
        print("collector: daily snapshot failed: %s" % exc, file=sys.stderr, flush=True)
        return None


def load_registry(conn: sqlite3.Connection, path: str) -> int:
    """Seed / refresh kits from registry.json. Returns the number of kits."""
    if not path or not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    kits = data.get("kits") or []
    created = now_rfc3339()
    for kit in kits:
        engine = kit["engine"]
        existing = conn.execute("SELECT engine FROM kits WHERE engine = ?", (engine,)).fetchone()
        values = (
            kit.get("tailscaleName") or engine,
            kit.get("school") or engine,
            kit["deploymentId"],
            kit.get("timezone"),
            kit.get("note") or "",
            engine,
        )
        if existing:
            conn.execute(
                """UPDATE kits SET tailscale_name = ?, school = ?, deployment_id = ?,
                   timezone = ?, note = ? WHERE engine = ?""",
                values,
            )
        else:
            conn.execute(
                """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
                   monitoring_enabled, last_pulled, note, created_at)
                   VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)""",
                (
                    engine,
                    values[0],
                    values[1],
                    values[2],
                    values[3],
                    values[4],
                    created,
                ),
            )
    conn.commit()
    return len(kits)


def kit_by_deployment(conn: sqlite3.Connection, deployment_id: str):
    return conn.execute("SELECT * FROM kits WHERE deployment_id = ?", (deployment_id,)).fetchone()


def kit_by_engine(conn: sqlite3.Connection, engine: str):
    return conn.execute("SELECT * FROM kits WHERE engine = ?", (engine,)).fetchone()
