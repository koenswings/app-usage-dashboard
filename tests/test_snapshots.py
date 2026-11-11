"""Daily UTC VACUUM INTO snapshots and 14-copy prune (idea#414)."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import db
from src import main as mainmod


def _conn(tmp: str):
    conn = db.connect(os.path.join(tmp, "usage.sqlite"))
    conn.execute("INSERT INTO meta(key, value) VALUES ('probe', '1')")
    conn.commit()
    return conn


class DailySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.backup = os.path.join(self.tmp, "backup")
        self.conn = _conn(self.tmp)
        self.day = datetime(2026, 11, 11, 15, 30, tzinfo=timezone.utc)

    def tearDown(self):
        self.conn.close()

    def test_once_per_utc_day(self):
        path = db.take_daily_snapshot(self.conn, self.backup, now=self.day)
        self.assertEqual(os.path.basename(path), "usage-2026-11-11.sqlite")
        self.assertTrue(os.path.isfile(path))
        # A later clock on the same UTC day must not write again.
        later = self.day + timedelta(hours=8)
        self.assertIsNone(db.take_daily_snapshot(self.conn, self.backup, now=later))
        self.assertEqual(db.list_snapshot_files(self.backup), [("2026-11-11", path)])

    def test_no_duplicate_after_restart(self):
        first = db.take_daily_snapshot(self.conn, self.backup, now=self.day)
        stat = os.stat(first)
        # Fresh connection, same backup dir and UTC day (process restart).
        other = db.connect(os.path.join(self.tmp, "usage.sqlite"))
        try:
            self.assertIsNone(db.take_daily_snapshot(other, self.backup, now=self.day))
        finally:
            other.close()
        self.assertEqual(os.stat(first).st_ino, stat.st_ino)
        self.assertEqual(os.stat(first).st_mtime_ns, stat.st_mtime_ns)
        self.assertEqual(len(db.list_snapshot_files(self.backup)), 1)

    def test_next_utc_day_writes_a_new_file(self):
        db.take_daily_snapshot(self.conn, self.backup, now=self.day)
        nxt = db.take_daily_snapshot(
            self.conn, self.backup, now=self.day + timedelta(days=1),
        )
        self.assertEqual(os.path.basename(nxt), "usage-2026-11-12.sqlite")
        self.assertEqual(
            [day for day, _ in db.list_snapshot_files(self.backup)],
            ["2026-11-12", "2026-11-11"],
        )

    def test_prune_keeps_14_newest_utc_days(self):
        start = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        for i in range(16):
            db.take_daily_snapshot(
                self.conn, self.backup, now=start + timedelta(days=i), keep=14,
            )
        days = [day for day, _ in db.list_snapshot_files(self.backup)]
        self.assertEqual(len(days), 14)
        self.assertEqual(days[0], "2026-11-04")
        self.assertEqual(days[-1], "2026-10-22")
        self.assertFalse(os.path.exists(os.path.join(self.backup, "usage-2026-10-20.sqlite")))
        self.assertFalse(os.path.exists(os.path.join(self.backup, "usage-2026-10-21.sqlite")))
        self.assertFalse(os.path.exists(db.snapshot_path(self.backup, "2026-10-20")))
        self.assertFalse(os.path.exists(db.snapshot_path(self.backup, "2026-10-21")))

    def test_prune_leaves_foreign_files_untouched(self):
        foreign = os.path.join(self.backup, "i431-cleanup-dep-idea03.sqlite")
        os.makedirs(self.backup, exist_ok=True)
        Path(foreign).write_bytes(b"do-not-touch")
        other = os.path.join(self.backup, "notes.txt")
        Path(other).write_text("keep\n")
        start = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        for i in range(16):
            db.take_daily_snapshot(
                self.conn, self.backup, now=start + timedelta(days=i), keep=14,
            )
        self.assertTrue(os.path.isfile(foreign))
        self.assertEqual(Path(foreign).read_bytes(), b"do-not-touch")
        self.assertEqual(Path(other).read_text(), "keep\n")
        self.assertEqual(len(db.list_snapshot_files(self.backup)), 14)

    def test_prune_leaves_hook_dump_untouched(self):
        """backup/usage.sqlite does not match usage-YYYY-MM-DD.sqlite."""
        hook = os.path.join(self.backup, "usage.sqlite")
        os.makedirs(self.backup, exist_ok=True)
        Path(hook).write_bytes(b"hook-dump-sentinel")
        start = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        for i in range(16):
            db.take_daily_snapshot(
                self.conn, self.backup, now=start + timedelta(days=i), keep=14,
            )
        self.assertTrue(os.path.isfile(hook))
        self.assertEqual(Path(hook).read_bytes(), b"hook-dump-sentinel")
        self.assertEqual(len(db.list_snapshot_files(self.backup)), 14)
        # Dated files landed in backup/daily/, not next to the hook dump.
        self.assertTrue(os.path.isdir(db.dated_snapshot_dir(self.backup)))
        self.assertFalse(os.path.exists(os.path.join(self.backup, "usage-2026-11-04.sqlite")))

    def test_migrate_moves_all_legacy_dated_files_into_daily(self):
        os.makedirs(self.backup, exist_ok=True)
        hook = os.path.join(self.backup, "usage.sqlite")
        Path(hook).write_bytes(b"hook-dump")
        foreign = os.path.join(self.backup, "notes.txt")
        Path(foreign).write_text("keep\n")
        days = ["2026-11-08", "2026-11-09", "2026-11-10"]
        for day in days:
            Path(os.path.join(self.backup, "usage-%s.sqlite" % day)).write_bytes(
                b"legacy-%s" % day.encode()
            )
        moved = db.migrate_dated_snapshots(self.backup)
        dests = [
            os.path.join(db.dated_snapshot_dir(self.backup), "usage-%s.sqlite" % day)
            for day in days
        ]
        self.assertEqual(sorted(moved), sorted(dests))
        for day, dest in zip(days, dests):
            self.assertTrue(os.path.isfile(dest), dest)
            self.assertEqual(Path(dest).read_bytes(), b"legacy-%s" % day.encode())
            self.assertFalse(os.path.exists(os.path.join(self.backup, "usage-%s.sqlite" % day)))
        self.assertEqual(Path(hook).read_bytes(), b"hook-dump")
        self.assertEqual(Path(foreign).read_text(), "keep\n")
        # Idempotent: a second run moves nothing and leaves the hook dump alone.
        self.assertEqual(db.migrate_dated_snapshots(self.backup), [])
        self.assertEqual(Path(hook).read_bytes(), b"hook-dump")
        for dest in dests:
            self.assertTrue(os.path.isfile(dest))

    def test_migrate_does_not_overwrite_existing_daily_copy(self):
        os.makedirs(db.dated_snapshot_dir(self.backup), exist_ok=True)
        dest = os.path.join(db.dated_snapshot_dir(self.backup), "usage-2026-11-10.sqlite")
        Path(dest).write_bytes(b"canonical-daily")
        leftover = os.path.join(self.backup, "usage-2026-11-10.sqlite")
        Path(leftover).write_bytes(b"old-path-leftover")
        hook = os.path.join(self.backup, "usage.sqlite")
        Path(hook).write_bytes(b"hook-dump")
        moved = db.migrate_dated_snapshots(self.backup)
        self.assertEqual(moved, [])
        self.assertEqual(Path(dest).read_bytes(), b"canonical-daily")
        # Leftover is gone so a backup cannot pack the old path.
        self.assertFalse(os.path.exists(leftover))
        self.assertEqual(Path(hook).read_bytes(), b"hook-dump")

    def test_migrate_legacy_backups_uses_data_dir_backup(self):
        data_dir = self.tmp
        backup = os.path.join(data_dir, "backup")
        os.makedirs(backup, exist_ok=True)
        Path(os.path.join(backup, "usage-2026-11-11.sqlite")).write_bytes(b"legacy")
        Path(os.path.join(backup, "usage.sqlite")).write_bytes(b"hook")
        moved = db.migrate_legacy_backups(data_dir)
        dest = os.path.join(backup, "daily", "usage-2026-11-11.sqlite")
        self.assertEqual(moved, [dest])
        self.assertTrue(os.path.isfile(dest))
        self.assertFalse(os.path.exists(os.path.join(backup, "usage-2026-11-11.sqlite")))
        self.assertEqual(Path(os.path.join(backup, "usage.sqlite")).read_bytes(), b"hook")
        self.assertEqual(db.migrate_legacy_backups(data_dir), [])
        # Missing backup dir is fine.
        self.assertEqual(db.migrate_legacy_backups(os.path.join(self.tmp, "no-such")), [])

    def test_error_is_non_fatal(self):
        def boom(_conn, _dest):
            raise RuntimeError("disk full")

        result = db.maybe_daily_snapshot(
            self.conn, self.backup, now=self.day, vacuum=boom,
        )
        self.assertIsNone(result)
        self.assertEqual(db.list_snapshot_files(self.backup), [])
        # No leftover temp from the failed attempt (temps live in backup/daily/).
        leftovers = [n for n in os.listdir(self.backup) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        daily = db.dated_snapshot_dir(self.backup)
        if os.path.isdir(daily):
            leftovers = [n for n in os.listdir(daily) if n.endswith(".tmp")]
            self.assertEqual(leftovers, [])

    def test_failed_vacuum_removes_temp_and_does_not_create_dest(self):
        def boom(_conn, dest):
            Path(dest).write_bytes(b"partial")
            raise sqlite3.OperationalError("vacuum failed")

        import sqlite3
        with self.assertRaises(sqlite3.OperationalError):
            db.take_daily_snapshot(self.conn, self.backup, now=self.day, vacuum=boom)
        dest = db.snapshot_path(self.backup, "2026-11-11")
        self.assertFalse(os.path.exists(dest))
        leftovers = [n for n in os.listdir(self.backup) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])
        daily = db.dated_snapshot_dir(self.backup)
        if os.path.isdir(daily):
            leftovers = [n for n in os.listdir(daily) if n.endswith(".tmp")]
            self.assertEqual(leftovers, [])


class SnapshotLoopTests(unittest.TestCase):
    def test_loop_survives_a_snapshot_error_and_still_records_uplink(self):
        tmp = tempfile.mkdtemp()
        conn = db.connect(os.path.join(tmp, "usage.sqlite"))
        conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('idea03','idea03','idea03 e2e','dep-idea03',NULL,1,NULL,'',?)""",
            (db.now_rfc3339(),),
        )
        conn.commit()
        fake = mainmod  # imported; use FakeLocalAPI from test_main_loop
        from test_main_loop import FakeLocalAPI, RUNNING_STATUS

        api = FakeLocalAPI(tmp, RUNNING_STATUS)
        key = os.path.join(tmp, "pull_key")
        Path(key).write_text("unused\n")
        calls = {"snap": 0, "pull": 0}

        def bad_snap(_conn):
            calls["snap"] += 1
            raise RuntimeError("snapshot exploded")

        def fake_pull(*_a, **_k):
            calls["pull"] += 1
            return "success"

        env = {
            "DATA_DIR": tmp,
            "TS_SOCKET": api.path,
            "TS_RESTART_FLAG": os.path.join(tmp, "restart-requested"),
            "PULL_KEY": key,
            "POLL_INTERVAL_S": "1",
            "UPLINK_INTERVAL_S": "1",
            "PULL_ONLINE_INTERVAL_S": "1",
            "SIDECAR_RESTART_AFTER_S": "600",
            "SIDECAR_RESTART_MIN_INTERVAL_S": "600",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        stop = threading.Event()
        try:
            thread = threading.Thread(
                target=mainmod.loop,
                kwargs={
                    "conn": conn,
                    "stop_event": stop,
                    "pull_fn": fake_pull,
                    "backup_dir": os.path.join(tmp, "backup"),
                    "snapshot_fn": bad_snap,
                },
                daemon=True,
            )
            thread.start()
            deadline = time.time() + 8
            while time.time() < deadline:
                n = conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0]
                if n > 0 and calls["snap"] > 0:
                    break
                time.sleep(0.1)
            n = conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0]
            self.assertGreater(calls["snap"], 0)
            self.assertGreater(n, 0)
            self.assertTrue(thread.is_alive())
        finally:
            stop.set()
            thread.join(timeout=3)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            api.close()
            conn.close()

    def test_loop_uses_maybe_daily_snapshot_and_swallows_vacuum_errors(self):
        """Default snapshot_fn is maybe_daily_snapshot: a vacuum error is non-fatal."""
        tmp = tempfile.mkdtemp()
        conn = db.connect(os.path.join(tmp, "usage.sqlite"))
        conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('idea03','idea03','dep','dep-idea03',NULL,1,NULL,'',?)""",
            (db.now_rfc3339(),),
        )
        conn.commit()
        from test_main_loop import FakeLocalAPI, RUNNING_STATUS

        api = FakeLocalAPI(tmp, RUNNING_STATUS)
        key = os.path.join(tmp, "pull_key")
        Path(key).write_text("unused\n")
        backup = os.path.join(tmp, "backup")
        os.makedirs(backup)

        def boom(_conn, _dest):
            raise RuntimeError("vacuum denied")

        def snap(conn_):
            return db.maybe_daily_snapshot(conn_, backup, vacuum=boom)

        def fake_pull(*_a, **_k):
            return "success"

        env = {
            "DATA_DIR": tmp,
            "TS_SOCKET": api.path,
            "TS_RESTART_FLAG": os.path.join(tmp, "restart-requested"),
            "PULL_KEY": key,
            "POLL_INTERVAL_S": "1",
            "UPLINK_INTERVAL_S": "1",
            "PULL_ONLINE_INTERVAL_S": "1",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        stop = threading.Event()
        try:
            thread = threading.Thread(
                target=mainmod.loop,
                kwargs={
                    "conn": conn,
                    "stop_event": stop,
                    "pull_fn": fake_pull,
                    "backup_dir": backup,
                    "snapshot_fn": snap,
                },
                daemon=True,
            )
            thread.start()
            deadline = time.time() + 8
            while time.time() < deadline:
                n = conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0]
                if n > 0:
                    break
                time.sleep(0.1)
            n = conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0]
            self.assertGreater(n, 0)
            self.assertTrue(thread.is_alive())
            self.assertEqual(db.list_snapshot_files(backup), [])
        finally:
            stop.set()
            thread.join(timeout=3)
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            api.close()
            conn.close()


if __name__ == "__main__":
    unittest.main()
