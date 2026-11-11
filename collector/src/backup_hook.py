"""idea#444 hook-mode snapshot and restore (Engine preHook / postHook / start).

The Engine (idea#444, §3.5) runs the preHook and postHook with
`docker compose exec -T` into the collector, then borg-creates the instance
folder without stopping the compose project (so the idea-hub sidecar stays
up). Field names (`method`, `preHook`, `postHook`, `hookTimeout`, `fallback`)
follow Axle's proposal on idea#444 and Steve's agreed answers; they are
centralised in compose and easy to rename when the Engine contract PR lands.

The preHook always writes a fresh consistent dump at
``$DATA_DIR/backup/usage.sqlite`` using SQLite's ``VACUUM INTO`` (never
``cp`` of the live db or its ``-wal``/``-shm``). The postHook removes only
that dump and this hook's temp files. On start, if the live db is absent
and the dump is present, ``maybe_restore_hook_dump`` copies it into place
after an integrity check and never overwrites an existing live db.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile

from . import db

HOOK_DUMP_NAME = "usage.sqlite"
HOOK_TMP_PREFIX = "usage.sqlite."
HOOK_TMP_SUFFIX = ".tmp"


class IntegrityError(RuntimeError):
    """The SQLite integrity_check pragma did not return ok."""


def hook_dump_path(data_dir: str) -> str:
    return os.path.join(data_dir, "backup", HOOK_DUMP_NAME)


def live_db_path(data_dir: str) -> str:
    return os.path.join(data_dir, "usage.sqlite")


def check_integrity(path: str) -> None:
    """Run PRAGMA integrity_check; raise IntegrityError unless the result is ok."""
    if not os.path.isfile(path):
        raise FileNotFoundError("no database at %s" % path)
    conn = sqlite3.connect(path, timeout=30)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    status = row[0] if row else None
    if status != "ok":
        raise IntegrityError("integrity_check failed for %s: %s" % (path, status))


def _remove_if_exists(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _cleanup_tmp(tmp: str) -> None:
    if tmp and os.path.exists(tmp):
        _remove_if_exists(tmp)


def write_hook_dump(data_dir: str, vacuum=None) -> str:
    """Write a fresh consistent dump to ``backup/usage.sqlite``.

    Opens the live db in a new connection (the collector may be writing),
    runs VACUUM INTO a temp file in the same directory, integrity-checks
    the temp file, then atomically renames it onto the stable dump path.
    Never copies the live db file. Raises on any failure (unlike
    ``maybe_daily_snapshot``, which swallows errors). The destination is
    overwritten when a leftover dump is present.

    Migrates leftover ``usage-YYYY-MM-DD.sqlite`` files into ``backup/daily/``
    first, so a backup never packs the old path even if the collector has
    not restarted (and even if this dump later fails).
    """
    backup_dir = os.path.join(data_dir, "backup")
    db.migrate_dated_snapshots(backup_dir)
    live = live_db_path(data_dir)
    if not os.path.isfile(live):
        raise FileNotFoundError("live database %s is missing" % live)
    os.makedirs(backup_dir, exist_ok=True)
    dest = hook_dump_path(data_dir)
    fd, tmp = tempfile.mkstemp(prefix=HOOK_TMP_PREFIX, suffix=HOOK_TMP_SUFFIX, dir=backup_dir)
    os.close(fd)
    os.unlink(tmp)
    src = sqlite3.connect(live, timeout=30)
    try:
        try:
            (vacuum or db.vacuum_into)(src, tmp)
            check_integrity(tmp)
            os.replace(tmp, dest)
        except Exception:
            _cleanup_tmp(tmp)
            raise
    finally:
        src.close()
    print("collector: wrote hook dump %s" % dest, file=sys.stderr, flush=True)
    return dest


def cleanup_hook_dump(data_dir: str) -> None:
    """Remove the hook dump and this hook's temp files. Missing files are fine.

    Dated daily snapshots (``backup/daily/usage-YYYY-MM-DD.sqlite``) and any
    other files in ``backup/`` are left alone.
    """
    backup_dir = os.path.join(data_dir, "backup")
    _remove_if_exists(hook_dump_path(data_dir))
    if not os.path.isdir(backup_dir):
        return
    for name in os.listdir(backup_dir):
        if name.startswith(HOOK_TMP_PREFIX) and name.endswith(HOOK_TMP_SUFFIX):
            _remove_if_exists(os.path.join(backup_dir, name))


def maybe_restore_hook_dump(data_dir: str) -> str | None:
    """If the live db is missing and the hook dump exists, restore it.

    Never overwrites an existing ``usage.sqlite``. Integrity-checks the dump
    (and the copy) before placing it. Stale ``-wal``/``-shm`` siblings of a
    missing live file are removed so they cannot attach to the restored db.
    Raises on integrity or I/O failure so the collector does not start with
    an empty db. Returns the live path when a restore happened, else None.
    """
    live = live_db_path(data_dir)
    dump = hook_dump_path(data_dir)
    if os.path.exists(live):
        return None
    if not os.path.isfile(dump):
        return None
    check_integrity(dump)
    parent = os.path.dirname(os.path.abspath(live)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="usage.restore.", suffix=".tmp", dir=parent)
    os.close(fd)
    os.unlink(tmp)
    try:
        shutil.copy2(dump, tmp)
        check_integrity(tmp)
        os.replace(tmp, live)
    except Exception:
        _cleanup_tmp(tmp)
        raise
    for suffix in ("-wal", "-shm"):
        _remove_if_exists(live + suffix)
    print("collector: restored %s from hook dump %s" % (live, dump), file=sys.stderr, flush=True)
    return live


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    data_dir = os.environ.get("DATA_DIR") or "/data"
    if not argv or argv[0] not in ("snapshot", "cleanup", "restore"):
        print("usage: python3 -m src.backup_hook snapshot|cleanup|restore", file=sys.stderr)
        return 2
    action = argv[0]
    try:
        if action == "snapshot":
            write_hook_dump(data_dir)
        elif action == "cleanup":
            cleanup_hook_dump(data_dir)
        else:
            maybe_restore_hook_dump(data_dir)
        return 0
    except Exception as exc:
        print("collector: backup hook %s failed: %s" % (action, exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
