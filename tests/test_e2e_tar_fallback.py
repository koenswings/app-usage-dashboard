import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "script" / "e2e-tar-fallback.sh"
INGEST = REPO / "script" / "ingest-usage-export.py"
SEND = REPO / "script" / "send-engine-command.mjs"
COMPOSE_TEXT = (REPO / "compose.yaml").read_text(encoding="utf-8")
VERSION = re.search(r'(?m)^  version: "([^"]+)"$', COMPOSE_TEXT).group(1)


def _compose_service_images():
    images = []
    in_services = False
    for line in COMPOSE_TEXT.splitlines():
        if line == "services:":
            in_services = True
            continue
        if in_services and line and not line.startswith("#") and line[0] not in " \t":
            in_services = False
        if in_services and line.strip().startswith("image:"):
            images.append(line.split("image:", 1)[1].strip().strip("\"'"))
    return images


def _service_tar_rel(image: str) -> str:
    name = image.split("@", 1)[0].replace("/", "_") + ".tar"
    return "services/" + name


def _command_lines(text: str):
    """Non-comment, non-empty script lines (for guard searches)."""
    out = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(stripped)
    return out


def _function_body(text: str, name: str) -> str:
    """Body of a top-level `name() { ... }` function, up to the next one."""
    match = re.search(r"^" + re.escape(name) + r"\(\) \{", text, re.M)
    if not match:
        raise AssertionError("missing function %s" % name)
    rest = text[match.end():]
    nxt = re.search(r"^[a-zA-Z_][a-zA-Z0-9_]*\(\) \{", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


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
            bundle = dest / "apps" / ("usage-dashboard-" + VERSION)
            info = bundle / "collector" / "build-info.json"
            sums = bundle / "SHA256SUMS"
            self.assertTrue((bundle / "compose.yaml").is_file())
            self.assertTrue(info.is_file())
            data = json.loads(info.read_text(encoding="utf-8"))
            commit = subprocess.check_output(
                ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
            ).strip()
            self.assertEqual(data["version"], VERSION)
            self.assertEqual(data["commit"], commit)
            self.assertTrue(sums.is_file())
            listed = sums.read_text(encoding="utf-8")
            self.assertIn("apps/usage-dashboard-%s/collector/build-info.json" % VERSION, listed)
            self.assertIn("apps/usage-dashboard-%s/compose.yaml" % VERSION, listed)
            planned = (dest / "dry-run-meta" / "planned-tars.txt").read_text(encoding="utf-8")
            for image in _compose_service_images():
                self.assertIn(_service_tar_rel(image), planned)
            self.assertNotIn("services/python:3.12-slim-bookworm.tar", planned)
            commands = (dest / "dry-run-meta" / "planned-commands.txt").read_text(encoding="utf-8")
            # idea#445: the web tar is the Engine-identical export of the pin, never a local build.
            pin = [l.split("image:", 1)[1].strip() for l in (REPO / "compose.yaml").read_text(encoding="utf-8").splitlines()
                   if l.strip().startswith("image: ghcr.io/koenswings/usage-dashboard-web")][0]
            self.assertIn("script/publish-web-image.sh --export-tar services --pin " + pin, commands)
            self.assertIn("script/verify-service-tar.sh compose.yaml services", commands)
            self.assertNotIn("docker build", commands)
            self.assertIn("ghcr.io/koenswings/usage-dashboard-web@" + pin.split("@", 1)[1], commands)
            self.assertIn("installApp usage-dashboard-" + VERSION, commands)
            self.assertIn("--source", commands)
            self.assertIn("--fresh", commands)
            self.assertIn("--keep", commands)
            self.assertIn("since 2026-10-01", commands)


    def test_post_install_asserts_repo_pin_and_tag(self):
        body = _function_body(self.text, "assert_web_pin_resolves")
        self.assertIn('"$WEB_REPO@$WEB_DIGEST"', body)
        self.assertIn('"$WEB_IMAGE"', body)
        self.assertIn("RepoDigests", body)
        self.assertIn('[ "$id_tag" = "$id_pin" ]', body)
        live = _function_body(self.text, "run_live")
        self.assertIn("assert_web_pin_resolves", live)
        self.assertIn('"$VERIFY" "$REPO/compose.yaml" /services', live)
        self.assertIn("export_web_tar", live)
        export = _function_body(self.text, "export_web_tar")
        self.assertIn('"$PUBLISH" --export-tar', export)
        # Teardown never untags the pinned web image.
        self.assertNotIn("docker image rm", _function_body(self.text, "remove_test_images"))
        # A container using the pin (the live hub) is never touched.
        self.assertIn("container_image_ids", _function_body(self.text, "unname_web_image"))

    def test_refuses_unpinned_web_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            (repo / "script").mkdir(parents=True)
            for f in (p for p in (REPO / "script").iterdir() if p.is_file()):
                (repo / "script" / f.name).write_bytes(f.read_bytes())
                (repo / "script" / f.name).chmod(f.stat().st_mode)
            text = (REPO / "compose.yaml").read_text(encoding="utf-8")
            text = re.sub(r"image: ghcr.io/koenswings/usage-dashboard-web:\S+@sha256:[0-9a-f]{64}",
                          "image: usage-dashboard-web:local-abc", text)
            (repo / "compose.yaml").write_text(text, encoding="utf-8")
            result = subprocess.run([str(repo / "script" / "e2e-tar-fallback.sh"), "--dry-run", "--dest", str(Path(tmp) / "d")],
                                    capture_output=True, text=True, cwd=str(repo))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be digest-pinned", result.stderr)

    def test_ingest_handles_root_owned_registry(self):
        """Host-side ingest must sudo (or match ownership) for root-owned ./data."""
        ensure = _function_body(self.text, "ensure_registry")
        install = _function_body(self.text, "install_into_instance_data")
        run_ingest = _function_body(self.text, "run_ingest_python")
        ingest = _function_body(self.text, "ingest_stream")
        self.assertIn("sudo -n", install)
        self.assertIn("sudo -n", run_ingest)
        self.assertIn("registry.json", ensure)
        self.assertIn("install_into_instance_data", ensure)
        self.assertIn("sudo -n cat", ensure)
        self.assertIn("run_ingest_python", ingest)
        self.assertIn("root-owned", self.text)
        # Direct writes of registry.json / ingest without the sudo fallback
        # must not be the only path: both helpers fall back to sudo -n when
        # the dest is not writable.
        self.assertIn('sudo -n cp "$src" "$dest"', install)
        self.assertIn("sudo -n python3", run_ingest)


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
