import json
import os
import subprocess
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

    def test_empty_env_falls_through_to_file(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"version": "1.0", "commit": "fromfileaaa"}, fh)
            os.environ["USAGE_DASHBOARD_BUILD_INFO"] = path
            os.environ["USAGE_DASHBOARD_COMMIT"] = ""
            os.environ["USAGE_DASHBOARD_VERSION"] = "  "
            self.assertEqual(dashboard_commit(), "fromfileaaa")
            self.assertEqual(dashboard_version(), "1.0")
        finally:
            os.remove(path)

    def test_write_build_info_script(self):
        repo = Path(__file__).resolve().parents[1]
        script = repo / "script" / "write-build-info.sh"
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            result = subprocess.run(
                [
                    str(script),
                    "--dest",
                    str(dest),
                    "--commit",
                    "0d929618656ec82819f29207613c88ad7813a0f1",
                    "--version",
                    "1.0",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            path = dest / "collector" / "build-info.json"
            self.assertTrue(path.is_file(), result.stdout)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "1.0")
            self.assertEqual(data["commit"], "0d929618656ec82819f29207613c88ad7813a0f1")
            os.environ["USAGE_DASHBOARD_BUILD_INFO"] = str(path)
            self.assertEqual(dashboard_commit(), "0d929618656ec82819f29207613c88ad7813a0f1")
            self.assertEqual(dashboard_version(), "1.0")


if __name__ == "__main__":
    unittest.main()
