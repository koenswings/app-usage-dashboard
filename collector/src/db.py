"""SQLite WAL store for the idea-hosted usage collector (proposal §7.5)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 1

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


def prune_backups(backup_dir: str, keep: int = 14) -> None:
    if not os.path.isdir(backup_dir):
        return
    files = sorted(
        (
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if name.endswith(".sqlite")
        ),
        key=os.path.getmtime,
        reverse=True,
    )
    for stale in files[keep:]:
        try:
            os.remove(stale)
        except OSError:
            pass


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
