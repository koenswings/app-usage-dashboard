import json
import os
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src.buildinfo import commit_from_mountinfo, dashboard_commit, dashboard_version


class BuildinfoTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "USAGE_DASHBOARD_COMMIT",
                "USAGE_DASHBOARD_VERSION",
                "USAGE_DASHBOARD_BUILD_INFO",
            )
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_defaults(self):
        self.assertEqual(dashboard_version(), "1.0")

    def test_env_overrides(self):
        os.environ["USAGE_DASHBOARD_VERSION"] = "1.0"
        os.environ["USAGE_DASHBOARD_COMMIT"] = "abc1234"
        self.assertEqual(dashboard_version(), "1.0")
        self.assertEqual(dashboard_commit(), "abc1234")

    def test_build_info_file(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"version": "1.0", "commit": "deadbeefcafebabe"}, fh)
            os.environ["USAGE_DASHBOARD_BUILD_INFO"] = path
            self.assertEqual(dashboard_version(), "1.0")
            self.assertEqual(dashboard_commit(), "deadbeefcafebabe")
        finally:
            os.remove(path)

    def test_bundle_path_from_mountinfo(self):
        text = (
            "36 24 0:34 /apps/usage-dashboard-"
            "f2d4adc64a370118383b9c97e9b31edb2c72d049/collector /app ro,relatime - bind /apps\n"
        )
        self.assertEqual(
            commit_from_mountinfo(text),
            "f2d4adc64a370118383b9c97e9b31edb2c72d049",
        )
        self.assertIsNone(commit_from_mountinfo("36 24 0:34 /workspace/app-usage-dashboard /app\n"))


if __name__ == "__main__":
    unittest.main()
