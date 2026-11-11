import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "script" / "e2e-tar-fallback.sh"
INGEST = REPO / "script" / "ingest-usage-export.py"
SEND = REPO / "script" / "send-engine-command.mjs"


def _command_lines(text: str):
    """Non-comment, non-empty script lines (for guard searches)."""
    out = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


class E2eTarFallbackTests(unittest.TestCase):
    def setUp(self):
        self.text = SCRIPT.read_text(encoding="utf-8")
        self.commands = "\n".join(_command_lines(self.text))

    def test_script_is_executable(self):
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        self.assertTrue(SEND.is_file())
        self.assertTrue(INGEST.is_file())
        self.assertTrue(os.access(INGEST, os.X_OK))

    def test_refuses_unless_pool_pi_claimed_by_kid(self):
        self.assertIn("idea03|idea04", self.text)
        self.assertIn("fleet claim", self.text)
        self.assertIn("Kid", self.text)
        self.assertIn("find_fleet_state", self.text)

    def test_hard_limits_are_not_invoked(self):
        joined = self.commands
        self.assertNotIn("rm -rf", joined)
        self.assertNotIn("pkill -f", joined)
        self.assertNotIn("pgrep -f", joined)
        # Whole-disk destructive tools must not appear as commands.
        for line in _command_lines(self.text):
            self.assertFalse(line == "dd" or line.startswith("dd "))
            self.assertNotIn("mkfs", line)
            self.assertFalse(line.startswith("wipe") or " wipefs" in f" {line}")

    def test_protected_targets_and_teardown_shape(self):
        self.assertIn("/disks/sdb1", self.text)
        self.assertIn("stopInstance $INSTANCE_ID $SYSTEM_DISK_ID", self.text)
        self.assertIn("removeInstance $INSTANCE_ID", self.text)
        self.assertIn("docker rm", self.text)
        self.assertNotIn("docker rm -v", self.commands)
        self.assertNotIn("docker rm --volumes", self.commands)
        self.assertIn("/home/pi/kid-quarantine", self.text)
        self.assertIn("idea#424", self.text)

    def test_keep_and_ingest_flags(self):
        self.assertIn("--keep", self.text)
        self.assertIn("--ingest-history", self.text)
        self.assertIn("20261111T001400/usage", self.text)
        self.assertIn("ingest-usage-export.py", self.text)
        self.assertIn("since 2026-10-01", self.text)
        self.assertIn("archive-and-clear", self.text)
        # Mentions the verb only as a prohibition, never as a command to run.
        for line in _command_lines(self.text):
            self.assertNotIn("archive-and-clear", line)

    def test_dry_run_stages_bundle_and_build_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "disk"
            dest.mkdir()
            result = subprocess.run(
                [str(SCRIPT), "--dry-run", "--dest", str(dest), "--keep", "--ingest-history"],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(REPO),
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            bundle = dest / "apps" / "usage-dashboard-1.0"
            info = bundle / "collector" / "build-info.json"
            sums = bundle / "SHA256SUMS"
            self.assertTrue((bundle / "compose.yaml").is_file())
            self.assertTrue(info.is_file())
            data = json.loads(info.read_text(encoding="utf-8"))
            commit = subprocess.check_output(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(data["version"], "1.0")
            self.assertEqual(data["commit"], commit)
            self.assertTrue(sums.is_file())
            listed = sums.read_text(encoding="utf-8")
            self.assertIn("apps/usage-dashboard-1.0/collector/build-info.json", listed)
            self.assertIn("apps/usage-dashboard-1.0/compose.yaml", listed)
            planned = (dest / "dry-run-meta" / "planned-tars.txt").read_text(encoding="utf-8")
            self.assertIn("services/usage-dashboard-web:1.0.tar", planned)
            self.assertIn("services/python:3.12-slim-bookworm.tar", planned)
            self.assertIn("services/tailscale_tailscale:v1.88.3.tar", planned)
            commands = (dest / "dry-run-meta" / "planned-commands.txt").read_text(encoding="utf-8")
            self.assertIn("installApp usage-dashboard-1.0", commands)
            self.assertIn("--source", commands)
            self.assertIn("--fresh", commands)
            self.assertIn("--keep", commands)
            self.assertIn("since 2026-10-01", commands)

    def test_ingest_helper_stores_export_stream(self):
        stream = """{"type":"presence","schema":"idea-usage-presence/1","day":"2026-10-28","payload":{"ts":"2026-10-28T09:00:00+01:00","day":"2026-10-28","bootId":"b","uptimeS":10,"ntpSynced":true}}
{"type":"day","schema":"idea-usage-day/1","day":"2026-10-28","instance":"nextcloud-files-b-001","payload":{"instance":"nextcloud-files-b-001","day":"2026-10-28","app":"nextcloud","hookStatus":"no-hook"}}
{"type":"end","schema":"idea-usage-export/1","since":"2026-10-01","engine":"idea03","usageMonitoring":"on","counts":{"day":1,"sample":0,"presence":1},"errors":0}
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ndjson = root / "export.ndjson"
            ndjson.write_text(stream, encoding="utf-8")
            registry = root / "registry.json"
            registry.write_text(
                json.dumps({
                    "kits": [{
                        "engine": "idea03",
                        "tailscaleName": "idea03",
                        "school": "proof",
                        "deploymentId": "dep-idea03-tar-e2e",
                        "timezone": "Europe/Brussels",
                    }]
                }),
                encoding="utf-8",
            )
            db_path = root / "usage.sqlite"
            result = subprocess.run(
                [
                    "python3",
                    str(INGEST),
                    "--db", str(db_path),
                    "--engine", "idea03",
                    "--deployment-id", "dep-idea03-tar-e2e",
                    "--stream", str(ndjson),
                    "--registry", str(registry),
                    "--pulled-at", "2026-11-11T02:00:00+01:00",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(REPO),
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["counts"]["day"], 1)
            self.assertEqual(summary["counts"]["presence"], 1)
            self.assertIn("2026-10-28", summary["dayDates"])
            self.assertTrue(db_path.is_file())


if __name__ == "__main__":
    unittest.main()
