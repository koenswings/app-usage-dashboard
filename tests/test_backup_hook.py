"""idea#444 hook-mode snapshot, cleanup, restore, and prune isolation."""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import backup_hook
from src import db
from src import main as mainmod


REPO = Path(__file__).resolve().parents[1]
COLLECTOR = REPO / "collector"
SNAPSHOT_SH = COLLECTOR / "scripts" / "backup-snapshot.sh"
CLEANUP_SH = COLLECTOR / "scripts" / "backup-cleanup.sh"


def _seed_db(tmp: str, rows: int = 3) -> str:
    live = os.path.join(tmp, "usage.sqlite")
    conn = db.connect(live)
    for i in range(rows):
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", ("row-%s" % i, str(i)))
    conn.commit()
    conn.close()
    return live


def _run_script(script: Path, data_dir: str, extra_env=None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATA_DIR"] = data_dir
    env["PYTHONPATH"] = str(COLLECTOR)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["sh", str(script)],
        capture_output=True,
        text=True,
        cwd=str(COLLECTOR),
        env=env,
    )


class HookDumpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.live = _seed_db(self.tmp, rows=5)

    def test_write_is_consistent_while_a_writer_is_active(self):
        conn = sqlite3.connect(self.live, timeout=30, check_same_thread=False)
        stop = threading.Event()
        errors = []

        def writer():
            try:
                n = 0
                while not stop.is_set():
                    conn.execute(
                        "INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, message)"
                        " VALUES (?, ?, ?, 1, 'hook', 'w')"
                        ,
                        ("kit", db.now_rfc3339(), db.now_rfc3339()),
                    )
                    conn.commit()
                    n += 1
                    time.sleep(0.001)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        time.sleep(0.05)
        dumps = []
        try:
            for _ in range(8):
                dest = backup_hook.write_hook_dump(self.tmp)
                dumps.append(dest)
                backup_hook.check_integrity(dest)
                snap = sqlite3.connect(dest)
                try:
                    snap.execute("PRAGMA foreign_keys = ON")
                    count = snap.execute("SELECT COUNT(*) FROM pull_log").fetchone()[0]
                    # Every committed row is complete; the dump is a readable SQLite file.
                    self.assertGreaterEqual(count, 0)
                    meta = snap.execute(
                        "SELECT COUNT(*) FROM meta WHERE key LIKE 'row-%'"
                    ).fetchone()[0]
                    self.assertEqual(meta, 5)
                finally:
                    snap.close()
                time.sleep(0.01)
        finally:
            stop.set()
            thread.join(timeout=3)
            conn.close()
        self.assertFalse(errors)
        self.assertTrue(os.path.isfile(backup_hook.hook_dump_path(self.tmp)))
        # The live file was never replaced by the dump.
        self.assertTrue(os.path.isfile(self.live))
        self.assertFalse(os.path.samefile(self.live, backup_hook.hook_dump_path(self.tmp)))

    def test_write_fails_when_live_db_is_missing(self):
        os.remove(self.live)
        with self.assertRaises(FileNotFoundError):
            backup_hook.write_hook_dump(self.tmp)
        self.assertFalse(os.path.exists(backup_hook.hook_dump_path(self.tmp)))

    def test_write_failure_removes_temp_and_does_not_leave_a_dump(self):
        def boom(_conn, dest):
            Path(dest).write_bytes(b"partial")
            raise sqlite3.OperationalError("vacuum failed")

        with self.assertRaises(sqlite3.OperationalError):
            backup_hook.write_hook_dump(self.tmp, vacuum=boom)
        self.assertFalse(os.path.exists(backup_hook.hook_dump_path(self.tmp)))
        backup = os.path.join(self.tmp, "backup")
        leftovers = [n for n in os.listdir(backup) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_write_overwrites_a_leftover_dump(self):
        first = backup_hook.write_hook_dump(self.tmp)
        Path(first).write_bytes(b"stale")
        second = backup_hook.write_hook_dump(self.tmp)
        self.assertEqual(first, second)
        backup_hook.check_integrity(second)
        snap = sqlite3.connect(second)
        try:
            self.assertEqual(
                snap.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'row-%'").fetchone()[0],
                5,
            )
        finally:
            snap.close()

    def test_never_copies_the_live_db_file(self):
        src = Path(COLLECTOR / "src" / "backup_hook.py").read_text(encoding="utf-8")
        script = SNAPSHOT_SH.read_text(encoding="utf-8")
        self.assertNotIn("shutil.copy", src.split("def maybe_restore_hook_dump")[0])
        commands = [
            line for line in script.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertFalse(any(re.search(r"\bcp\b", line) for line in commands), script)
        # write_hook_dump uses vacuum_into, not a file copy of the live db.
        dest = backup_hook.write_hook_dump(self.tmp)
        self.assertFalse(os.path.samefile(self.live, dest))


class LegacyMigrateInHookAndStartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.backup = os.path.join(self.tmp, "backup")
        os.makedirs(self.backup, exist_ok=True)
        for day in ("2026-11-09", "2026-11-10"):
            Path(os.path.join(self.backup, "usage-%s.sqlite" % day)).write_bytes(
                b"legacy-%s" % day.encode()
            )
        Path(os.path.join(self.backup, "usage.sqlite")).write_bytes(b"old-hook-dump")

    def _assert_migrated(self):
        daily = os.path.join(self.backup, "daily")
        for day in ("2026-11-09", "2026-11-10"):
            dest = os.path.join(daily, "usage-%s.sqlite" % day)
            self.assertTrue(os.path.isfile(dest), dest)
            self.assertEqual(Path(dest).read_bytes(), b"legacy-%s" % day.encode())
            self.assertFalse(os.path.exists(os.path.join(self.backup, "usage-%s.sqlite" % day)))

    def test_pre_hook_migrates_legacy_files_before_the_dump(self):
        _seed_db(self.tmp)
        dest = backup_hook.write_hook_dump(self.tmp)
        self._assert_migrated()
        backup_hook.check_integrity(dest)
        # Hook dump was rewritten as the consistent dump, not left as the sentinel.
        self.assertNotEqual(Path(dest).read_bytes(), b"old-hook-dump")
        # Dated files stay in daily/ next to the hook dump, not in the parent.
        self.assertTrue(os.path.isfile(os.path.join(self.backup, "usage.sqlite")))

    def test_pre_hook_migrates_even_when_the_dump_fails(self):
        # No live db: dump fails, but leftovers must still be moved so a
        # HOOK_FALLBACK backup cannot pack them.
        with self.assertRaises(FileNotFoundError):
            backup_hook.write_hook_dump(self.tmp)
        self._assert_migrated()
        self.assertEqual(
            Path(os.path.join(self.backup, "usage.sqlite")).read_bytes(),
            b"old-hook-dump",
        )

    def test_snapshot_script_migrates_legacy_files(self):
        _seed_db(self.tmp)
        result = _run_script(SNAPSHOT_SH, self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self._assert_migrated()
        backup_hook.check_integrity(backup_hook.hook_dump_path(self.tmp))

    def test_main_migrates_legacy_files_at_startup(self):
        _seed_db(self.tmp)
        env = {
            "DATA_DIR": self.tmp,
            "COLLECTOR_BIND": "127.0.0.1:0",
            "IDEA_USAGE_KOEN_PASSWORD": "koen911!",
            "IDEA_USAGE_MARCO_PASSWORD": "marco911!",
            "IDEA_USAGE_ONCE": "1",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        served = {}

        def fake_serve(conn, bind):
            served["opened"] = True

            class _Srv:
                def serve_forever(self):
                    return None

            return _Srv()

        orig_serve = mainmod.serve
        mainmod.serve = fake_serve
        try:
            self.assertEqual(mainmod.main(), 0)
            self.assertTrue(served.get("opened"))
            self._assert_migrated()
            self.assertEqual(
                Path(os.path.join(self.backup, "usage.sqlite")).read_bytes(),
                b"old-hook-dump",
            )
        finally:
            mainmod.serve = orig_serve
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed_db(self.tmp)

    def test_cleanup_removes_dump_and_is_idempotent(self):
        dest = backup_hook.write_hook_dump(self.tmp)
        dated = os.path.join(self.tmp, "backup", "daily", "usage-2026-11-11.sqlite")
        os.makedirs(os.path.dirname(dated), exist_ok=True)
        Path(dated).write_bytes(b"daily")
        leftover_tmp = os.path.join(self.tmp, "backup", "usage.sqlite.abc.tmp")
        Path(leftover_tmp).write_bytes(b"tmp")
        foreign = os.path.join(self.tmp, "backup", "notes.txt")
        Path(foreign).write_text("keep\n")
        backup_hook.cleanup_hook_dump(self.tmp)
        self.assertFalse(os.path.exists(dest))
        self.assertFalse(os.path.exists(leftover_tmp))
        self.assertTrue(os.path.isfile(dated))
        self.assertEqual(Path(foreign).read_text(), "keep\n")
        # Second call, and a call with nothing present, must succeed.
        backup_hook.cleanup_hook_dump(self.tmp)
        backup_hook.cleanup_hook_dump(os.path.join(self.tmp, "missing-root"))

    def test_cleanup_tolerates_a_missing_backup_dir(self):
        backup_hook.cleanup_hook_dump(self.tmp)  # no dump written
        backup_hook.cleanup_hook_dump(tempfile.mkdtemp())


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.live = _seed_db(self.tmp, rows=4)
        self.dump = backup_hook.write_hook_dump(self.tmp)

    def test_restore_only_when_live_db_is_absent(self):
        existing = Path(self.live).read_bytes()
        self.assertIsNone(backup_hook.maybe_restore_hook_dump(self.tmp))
        self.assertEqual(Path(self.live).read_bytes(), existing)
        # Same after the live file is a non-empty sqlite (never overwrite).
        os.remove(self.live)
        restored = backup_hook.maybe_restore_hook_dump(self.tmp)
        self.assertEqual(restored, self.live)
        backup_hook.check_integrity(self.live)
        conn = sqlite3.connect(self.live)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'row-%'").fetchone()[0],
                4,
            )
        finally:
            conn.close()
        # Dump is kept (copy, not move) so a failed start can retry.
        self.assertTrue(os.path.isfile(self.dump))

    def test_restore_is_a_no_op_when_both_are_absent(self):
        os.remove(self.live)
        os.remove(self.dump)
        self.assertIsNone(backup_hook.maybe_restore_hook_dump(self.tmp))
        self.assertFalse(os.path.exists(self.live))

    def test_restore_rejects_a_corrupt_dump_and_does_not_create_live(self):
        os.remove(self.live)
        Path(self.dump).write_bytes(b"not-a-database")
        with self.assertRaises(Exception):
            backup_hook.maybe_restore_hook_dump(self.tmp)
        self.assertFalse(os.path.exists(self.live))

    def test_restore_drops_stale_wal_shm(self):
        os.remove(self.live)
        wal = self.live + "-wal"
        shm = self.live + "-shm"
        Path(wal).write_bytes(b"stale-wal")
        Path(shm).write_bytes(b"stale-shm")
        backup_hook.maybe_restore_hook_dump(self.tmp)
        self.assertTrue(os.path.isfile(self.live))
        self.assertFalse(os.path.exists(wal))
        self.assertFalse(os.path.exists(shm))

    def test_main_restores_before_opening_the_db(self):
        """main() applies the hook dump when usage.sqlite is absent, then serves."""
        os.remove(self.live)
        # operators seed + a free bind.
        env = {
            "DATA_DIR": self.tmp,
            "COLLECTOR_BIND": "127.0.0.1:0",
            "IDEA_USAGE_KOEN_PASSWORD": "koen911!",
            "IDEA_USAGE_MARCO_PASSWORD": "marco911!",
            "IDEA_USAGE_ONCE": "1",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        # serve() uses the bind string; port 0 may not work with the http server helper.
        # Instead, call maybe_restore through main up to connect by stubbing serve/loop.
        served = {}

        def fake_serve(conn, bind):
            served["opened"] = True
            served["rows"] = conn.execute(
                "SELECT COUNT(*) FROM meta WHERE key LIKE 'row-%'"
            ).fetchone()[0]
            served["path"] = self.live
            served["conn"] = conn

            class _Srv:
                def serve_forever(self):
                    return None

            return _Srv()

        orig_serve = mainmod.serve
        mainmod.serve = fake_serve
        try:
            rc = mainmod.main()
            self.assertEqual(rc, 0)
            self.assertTrue(served.get("opened"))
            self.assertEqual(served.get("rows"), 4)
            self.assertTrue(os.path.isfile(self.live))
        finally:
            mainmod.serve = orig_serve
            conn = served.get("conn")
            if conn is not None:
                conn.close()
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class ScriptExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_snapshot_script_succeeds_and_cleanup_is_idempotent(self):
        _seed_db(self.tmp)
        result = _run_script(SNAPSHOT_SH, self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        dump = backup_hook.hook_dump_path(self.tmp)
        self.assertTrue(os.path.isfile(dump))
        backup_hook.check_integrity(dump)
        cleaned = _run_script(CLEANUP_SH, self.tmp)
        self.assertEqual(cleaned.returncode, 0, cleaned.stderr + cleaned.stdout)
        self.assertFalse(os.path.exists(dump))
        again = _run_script(CLEANUP_SH, self.tmp)
        self.assertEqual(again.returncode, 0, again.stderr + again.stdout)

    def test_snapshot_script_exits_nonzero_when_live_db_is_missing(self):
        result = _run_script(SNAPSHOT_SH, self.tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing", (result.stderr + result.stdout).lower())
        self.assertFalse(os.path.exists(backup_hook.hook_dump_path(self.tmp)))

    def test_snapshot_script_exits_nonzero_when_vacuum_fails(self):
        _seed_db(self.tmp)
        # Point DATA_DIR at a live db path whose parent is not writable for backup/?
        # Easier: replace live db with a non-db file so VACUUM INTO fails.
        Path(os.path.join(self.tmp, "usage.sqlite")).write_bytes(b"not-a-db")
        result = _run_script(SNAPSHOT_SH, self.tmp)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.exists(backup_hook.hook_dump_path(self.tmp)))


class RegistryAndOperatorsDecisionTests(unittest.TestCase):
    def test_operators_json_is_written_atomically(self):
        src = (COLLECTOR / "src" / "auth.py").read_text(encoding="utf-8")
        self.assertIn("tempfile.mkstemp", src)
        self.assertIn("os.replace", src)
        # The write helper uses a temp file in the same directory, then replace.
        self.assertIn("def _write_file", src)
        block = src.split("def _write_file", 1)[1].split("def ensure_operators", 1)[0]
        self.assertIn("os.replace", block)
        self.assertIn("mkstemp", block)

    def test_collector_does_not_write_registry_json(self):
        src = (COLLECTOR / "src" / "db.py").read_text(encoding="utf-8")
        # load_registry only reads the file.
        block = src.split("def load_registry", 1)[1].split("def kit_by_deployment", 1)[0]
        self.assertIn("json.load", block)
        self.assertNotIn("json.dump", block)
        self.assertNotIn("os.replace", block)


if __name__ == "__main__":
    unittest.main()
