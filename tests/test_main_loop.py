"""LocalAPI unix-socket, watchdog policy, and compose volume rules (idea#415 item 14)."""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import db
from src import main as mainmod


REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "compose.yaml"

RUNNING_STATUS = {
    "BackendState": "Running",
    "Self": {
        "Online": True,
        "HostName": "idea-hub",
        "DNSName": "idea-hub.tail2d60.ts.net.",
        "TailscaleIPs": ["100.75.102.57"],
    },
    "Peer": {
        "key1": {
            "HostName": "idea03",
            "DNSName": "idea03.tail2d60.ts.net.",
            "Online": True,
            "LastSeen": "0001-01-01T00:00:00Z",
            "Relay": "ams",
            "CurAddr": "",
        }
    },
}


class _UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True
    status = None
    requests = None
    status_code = 200


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_GET(self):
        self.server.requests.append({"path": self.path, "host": self.headers.get("Host")})
        if self.server.status is None:
            self.send_response(500)
            self.end_headers()
            return
        body = json.dumps(self.server.status).encode("utf-8")
        self.send_response(self.server.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.server.status_code == 200:
            self.wfile.write(body)


class FakeLocalAPI:
    def __init__(self, directory, status):
        self.path = os.path.join(directory, "tailscaled.sock")
        if os.path.exists(self.path):
            os.unlink(self.path)
        self.server = _UnixHTTPServer(self.path, _Handler)
        self.server.status = status
        self.server.requests = []
        self.server.status_code = 200
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        if os.path.exists(self.path):
            os.unlink(self.path)


class DecideSidecarActionTests(unittest.TestCase):
    def test_running_never_requests_restart(self):
        decision = mainmod.decide_sidecar_action(
            RUNNING_STATUS, None, now=10_000, bad_since=0, last_restart_at=0,
            restart_after_s=10, restart_min_interval_s=10,
        )
        self.assertTrue(decision["running"])
        self.assertFalse(decision["request_restart"])
        self.assertTrue(decision["record_uplink"])
        self.assertTrue(decision["close_gap"])
        self.assertIsNone(decision["open_gap_reason"])

    def test_status_error_does_not_restart_inside_the_window(self):
        now = 1_000.0
        decision = mainmod.decide_sidecar_action(
            None, "FileNotFoundError: missing", now=now, bad_since=now - 60,
            last_restart_at=0, restart_after_s=600, restart_min_interval_s=600,
        )
        self.assertFalse(decision["running"])
        self.assertFalse(decision["request_restart"])
        self.assertEqual(decision["open_gap_reason"], "sidecar-offline")
        self.assertFalse(decision["record_uplink"])
        self.assertIn("backing off", decision["log"])

    def test_status_error_requests_restart_after_the_window(self):
        now = 10_000.0
        decision = mainmod.decide_sidecar_action(
            None, "ConnectionRefusedError", now=now, bad_since=now - 600,
            last_restart_at=0, restart_after_s=600, restart_min_interval_s=600,
        )
        self.assertTrue(decision["request_restart"])
        self.assertEqual(decision["open_gap_reason"], "sidecar-offline")

    def test_restart_is_rate_limited(self):
        now = 10_000.0
        decision = mainmod.decide_sidecar_action(
            None, "error", now=now, bad_since=now - 10_000,
            last_restart_at=now - 30, restart_after_s=600, restart_min_interval_s=600,
        )
        self.assertFalse(decision["request_restart"])

    def test_needs_login_never_restarts_or_joins(self):
        status = {"BackendState": "NeedsLogin", "Self": {"Online": False}, "LoggedOut": True}
        # Even after a long outage, never restart and never join.
        decision = mainmod.decide_sidecar_action(
            status, None, now=10_000, bad_since=0, last_restart_at=0,
            restart_after_s=10, restart_min_interval_s=10,
        )
        self.assertTrue(decision["logged_out"])
        self.assertFalse(decision["request_restart"])
        self.assertFalse(decision["running"])
        self.assertEqual(decision["open_gap_reason"], "sidecar-logged-out")
        self.assertIn("not joining", decision["log"])
        self.assertIsNone(decision["bad_since"])

    def test_logged_out_flag_without_needs_login(self):
        status = {"BackendState": "Stopped", "LoggedOut": True}
        decision = mainmod.decide_sidecar_action(
            status, None, now=10_000, bad_since=0, last_restart_at=0,
            restart_after_s=10, restart_min_interval_s=10,
        )
        self.assertTrue(decision["logged_out"])
        self.assertFalse(decision["request_restart"])


class UnixLocalAPILoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmp, "usage.sqlite"))
        self.conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('idea03','idea03','idea03 e2e','dep-idea03',NULL,1,NULL,'',?)""",
            (db.now_rfc3339(),),
        )
        self.conn.commit()
        self.fake = FakeLocalAPI(self.tmp, RUNNING_STATUS)
        self.key = os.path.join(self.tmp, "pull_key")
        Path(self.key).write_text("unused\n")
        self.pulls = []

        def fake_pull(conn, engine, host, key, since, socks=None):
            self.pulls.append({"engine": engine, "host": host, "since": since, "socks": socks})
            conn.execute(
                """INSERT INTO pull_log(engine, started_at, finished_at, ok, kind, since_day, message, counts)
                   VALUES (?, ?, ?, 1, 'success', ?, 'ok', NULL)""",
                (engine, db.now_rfc3339(), db.now_rfc3339(), since),
            )
            conn.execute("UPDATE kits SET last_pulled = ? WHERE engine = ?", (db.now_rfc3339(), engine))
            conn.commit()
            return "success"

        self.fake_pull = fake_pull
        self._env = {
            "TS_SOCKET": self.fake.path,
            "TS_RESTART_FLAG": os.path.join(self.tmp, "restart-requested"),
            "PULL_KEY": self.key,
            "POLL_INTERVAL_S": "1",
            "UPLINK_INTERVAL_S": "1",
            "PULL_ONLINE_INTERVAL_S": "1",
            "SIDECAR_RESTART_AFTER_S": "600",
            "SIDECAR_RESTART_MIN_INTERVAL_S": "600",
            "TS_SOCKS5": "127.0.0.1:1055",
        }
        self._saved = {k: os.environ.get(k) for k in self._env}
        os.environ.update(self._env)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.fake.close()
        self.conn.close()

    def test_running_online_peers_write_uplink_and_pull(self):
        stop = threading.Event()
        thread = threading.Thread(
            target=mainmod.loop,
            kwargs={"conn": self.conn, "stop_event": stop, "pull_fn": self.fake_pull},
            daemon=True,
        )
        thread.start()
        deadline = time.time() + 8
        while time.time() < deadline:
            n = self.conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0]
            if n > 0 and self.pulls:
                break
            time.sleep(0.1)
        stop.set()
        thread.join(timeout=3)
        self.assertGreater(self.conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0], 0)
        self.assertTrue(self.pulls)
        self.assertEqual(self.pulls[0]["engine"], "idea03")
        self.assertEqual(self.pulls[0]["host"], "idea03")
        hosts = {r["host"] for r in self.fake.server.requests}
        self.assertIn(mainmod.LOCALAPI_HOST, hosts)
        self.assertFalse(os.path.exists(self._env["TS_RESTART_FLAG"]))

    def test_status_error_does_not_write_restart_flag_inside_the_window(self):
        self.fake.close()
        # Recreate a path that nothing listens on.
        os.environ["TS_SOCKET"] = os.path.join(self.tmp, "missing.sock")
        stop = threading.Event()
        thread = threading.Thread(
            target=mainmod.loop,
            kwargs={"conn": self.conn, "stop_event": stop, "pull_fn": self.fake_pull},
            daemon=True,
        )
        thread.start()
        time.sleep(1.5)
        stop.set()
        thread.join(timeout=3)
        self.assertFalse(os.path.exists(self._env["TS_RESTART_FLAG"]))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0], 0)
        self.assertFalse(self.pulls)
        gap = self.conn.execute("SELECT reason, end FROM collector_gaps").fetchone()
        self.assertIsNotNone(gap)
        self.assertEqual(gap["reason"], "sidecar-offline")
        self.assertIsNone(gap["end"])

    def test_needs_login_does_not_restart_or_join(self):
        self.fake.server.status = {"BackendState": "NeedsLogin", "Self": {}, "LoggedOut": True}
        joined = []

        def forbidden_pull(*_a, **_k):
            joined.append("pull")
            raise AssertionError("must not pull or join when NeedsLogin")

        stop = threading.Event()
        thread = threading.Thread(
            target=mainmod.loop,
            kwargs={"conn": self.conn, "stop_event": stop, "pull_fn": forbidden_pull},
            daemon=True,
        )
        thread.start()
        time.sleep(1.5)
        stop.set()
        thread.join(timeout=3)
        self.assertFalse(os.path.exists(self._env["TS_RESTART_FLAG"]))
        self.assertFalse(joined)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0], 0)
        gap = self.conn.execute("SELECT reason FROM collector_gaps").fetchone()
        self.assertEqual(gap["reason"], "sidecar-logged-out")

    def test_localapi_status_uses_cli_host_header(self):
        status, err = mainmod.localapi_status(self.fake.path)
        self.assertIsNone(err)
        self.assertEqual(status["BackendState"], "Running")
        self.assertEqual(self.fake.server.requests[-1]["host"], "local-tailscaled.sock")
        self.assertEqual(self.fake.server.requests[-1]["path"], "/localapi/v0/status")


class ComposeVolumeTests(unittest.TestCase):
    def test_collector_does_not_mount_state_dir(self):
        text = COMPOSE.read_text()
        # Split out the collector service block the same way the packaging check does.
        lines = text.splitlines()
        in_collector = False
        block = []
        for line in lines:
            if line == "  collector:":
                in_collector = True
                block = [line]
                continue
            if in_collector:
                if line.startswith("  ") and not line.startswith("   ") and line.endswith(":") and line != "  collector:":
                    if line[2] != " " and not line.startswith("  #"):
                        # next service
                        if not line.startswith("  -") and line[2:3].isalpha():
                            in_collector = False
                            continue
                if line.startswith("  ") or line.startswith("\t") or line.startswith("    ") or not line.strip() or line.lstrip().startswith("#"):
                    if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":") and not line.strip().startswith("#") and line.split(":")[0].strip() in ("web", "tailscale"):
                        in_collector = False
                        continue
                    block.append(line)
        body = "\n".join(block)
        self.assertIn("collector:", body)
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and ":" in stripped:
                src = stripped[2:].split(":", 1)[0]
                self.assertNotEqual(
                    src, "./data/tailscale",
                    "collector must not bind-mount the sidecar state dir (node key): %s" % stripped,
                )
        self.assertIn("./data/tailscale-run:/var/run/tailscale", body)
        self.assertIn("tmpfs:", body)
        self.assertIn("/data/tailscale", body)
        self.assertIn("TS_SOCKET=/var/run/tailscale/tailscaled.sock", body)
        self.assertNotIn("TS_LOCALAPI=", body)
        self.assertNotIn("TS_STATE_DIR=/data/tailscale", body)

    def test_sidecar_shares_socket_dir_and_keeps_state_separate(self):
        text = COMPOSE.read_text()
        # tailscale service
        start = text.index("  tailscale:")
        end = text.index("  collector:")
        body = text[start:end]
        self.assertIn("./data/tailscale:/var/lib/tailscale", body)
        self.assertIn("./data/tailscale-run:/var/run/tailscale", body)
        self.assertIn("TS_SOCKET=/var/run/tailscale/tailscaled.sock", body)
        self.assertNotIn("TS_LOCAL_ADDR_PORT=", body)
        self.assertIn("/var/run/tailscale/tailscaled.sock", body)  # healthcheck


if __name__ == "__main__":
    unittest.main()
