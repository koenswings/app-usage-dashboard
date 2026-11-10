import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import db
from src.parse import DisabledExport, interpret_export
from src.pull import store_export


class PullStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmp, "usage.sqlite"))
        self.conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('happy-zebra','happy-zebra','Nharira','dep-nharira',NULL,NULL,NULL,'',?)""",
            (db.now_rfc3339(),),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_store_day_uses_instance_field(self):
        parsed = {
            "presence": [],
            "days": [{
                "type": "day",
                "day": "2026-11-09",
                "instance": "kolibri-a",
                "payload": {
                    "schema": "idea-usage-day/1",
                    "engine": "happy-zebra",
                    "day": "2026-11-09",
                    "app": "kolibri",
                    "instance": "kolibri-a",
                    "hookStatus": "ok",
                    "listed": True,
                    "demo": False,
                },
            }],
            "samples": [],
            "end": {"counts": {"day": 1}},
        }
        store_export(self.conn, "happy-zebra", parsed, "2026-11-10T10:00:00+01:00", "dep-nharira")
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM daily_summaries").fetchone()
        self.assertEqual(row["instance"], "kolibri-a")
        self.assertEqual(row["hook_status"], "ok")
        kit = self.conn.execute("SELECT last_pulled, monitoring_enabled FROM kits").fetchone()
        self.assertEqual(kit["last_pulled"], "2026-11-10T10:00:00+01:00")
        self.assertEqual(kit["monitoring_enabled"], 1)

    def test_disabled_exit_is_not_invalid(self):
        with self.assertRaises(DisabledExport):
            interpret_export(10, "", "disabled")


if __name__ == "__main__":
    unittest.main()
