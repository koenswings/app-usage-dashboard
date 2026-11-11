"""Identity guard: ride out a short NoState blip, fail closed on real identity loss."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import db
from src import identity as ident
from src import main as mainmod
from test_main_loop import FakeLocalAPI, RUNNING_STATUS


KNOWN = "1382c2eab7500ea4" + "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
ZERO = "0" * 64
OTHER = "abcdef0123456789" + "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def running(pub=KNOWN, **extra):
    status = {
        "BackendState": "Running",
        "AuthURL": "",
        "Self": {
            "Online": True,
            "HostName": "idea-hub",
            "PublicKey": "nodekey:" + pub,
            "TailscaleIPs": ["100.75.102.57"],
        },
    }
    status.update(extra)
    return status


def nostate_zeroed():
    return {
        "BackendState": "NoState",
        "AuthURL": "",
        "LoggedOut": False,
        "Self": {
            "Online": False,
            "PublicKey": "nodekey:" + ZERO,
        },
    }


def starting(pub=ZERO):
    return {
        "BackendState": "Starting",
        "AuthURL": "",
        "Self": {"Online": False, "PublicKey": "nodekey:" + pub},
    }


class DecideIdentityTests(unittest.TestCase):
    def setUp(self):
        self.state = ident.IdentityState()

    def tick(self, status, now, error=None, stamp=None, **kw):
        return ident.decide_identity(
            status, error, now, self.state, blip_s=15, blip_polls=0, stamp=stamp, **kw
        )

    def test_20_10_nostate_zeroed_starting_then_same_key_is_ridden_out(self):
        """idea03 2026-11-11 20:10 Europe/Brussels wrap restart sequence.

        Unpause at 20:10:08; ~2s later LocalAPI reported NoState with a
        zeroed PublicKey and no AuthURL; containerboot logged NoState →
        Starting → Running in about one second; by 20:10:45 the prefix
        1382c2eab7500ea4 was back and the state inode was unchanged.
        The previous operator guard treated the zeroed blip as a key
        change and stopped the collector. This guard must not.
        """
        # 20:10:08 Running, known key, inode 7048947 / size 2358 (unchanged).
        stamp = (7048947, 2358)
        d = self.tick(running(), now=1_000.0, stamp=stamp)
        self.assertFalse(d.fail_closed)
        self.assertFalse(d.in_blip)
        self.assertEqual(self.state.known_key, KNOWN)
        self.assertEqual(self.state.stamp, stamp)

        # 20:10:10 NoState, zeroed PublicKey, NeedLogin=false, AuthURL empty.
        d = self.tick(nostate_zeroed(), now=1_002.0, stamp=stamp)
        self.assertFalse(d.fail_closed, d.log)
        self.assertTrue(d.in_blip)
        self.assertIn("riding it out", d.log)
        self.assertIn("zeroed", d.log)

        # 20:10:10.5 Starting (still no AuthURL, same inode).
        d = self.tick(starting(), now=1_002.5, stamp=stamp)
        self.assertFalse(d.fail_closed, d.log)
        self.assertTrue(d.in_blip)

        # 20:10:11 Running, same non-zero key, same inode.
        d = self.tick(running(), now=1_003.0, stamp=stamp)
        self.assertFalse(d.fail_closed)
        self.assertFalse(d.in_blip)
        self.assertFalse(self.state.failed)
        self.assertIsNone(self.state.reason)
        self.assertEqual(self.state.known_key, KNOWN)
        self.assertEqual(self.state.stamp, stamp)

    def test_localapi_timeout_is_not_an_identity_failure(self):
        self.tick(running(), now=1.0)
        d = self.tick(None, now=2.0, error="TimeoutError: timed out")
        self.assertFalse(d.fail_closed)
        self.assertFalse(d.in_blip)
        self.assertFalse(self.state.failed)

    def test_different_nonzero_key_fails_closed_immediately(self):
        self.tick(running(KNOWN), now=1.0)
        d = self.tick(running(OTHER), now=2.0)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "nodekey-changed")
        self.assertEqual(d.gap_reason, ident.GAP_IDENTITY)
        self.assertIn("1382c2eab7500ea4", d.log)
        self.assertIn("abcdef0123456789", d.log)
        # A later return to the original key stays failed (latched).
        d2 = self.tick(running(KNOWN), now=3.0)
        self.assertTrue(d2.fail_closed)
        self.assertEqual(d2.reason, "nodekey-changed")

    def test_needs_login_fails_closed_immediately(self):
        self.tick(running(), now=1.0)
        status = {
            "BackendState": "NeedsLogin",
            "AuthURL": "",
            "LoggedOut": True,
            "Self": {"Online": False, "PublicKey": "nodekey:" + KNOWN},
        }
        d = self.tick(status, now=2.0)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "logged-out")
        self.assertEqual(d.gap_reason, ident.GAP_LOGGED_OUT)
        self.assertIn("not joining", d.log)

    def test_logged_out_without_needs_login_fails_closed(self):
        self.tick(running(), now=1.0)
        status = {"BackendState": "Stopped", "LoggedOut": True, "Self": {}}
        d = self.tick(status, now=2.0)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "logged-out")

    def test_authurl_fails_closed_immediately(self):
        self.tick(running(), now=1.0)
        # Value is present but the log must not echo it.
        status = running()
        status["AuthURL"] = "https://login.tailscale.com/a/not-a-real-login"
        d = self.tick(status, now=2.0)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "auth-url")
        self.assertEqual(d.gap_reason, ident.GAP_IDENTITY)
        self.assertNotIn("login.tailscale.com", d.log or "")
        self.assertNotIn("not-a-real-login", d.log or "")

    def test_authurl_on_self_also_fails_closed(self):
        self.tick(running(), now=1.0)
        status = running()
        status["Self"] = dict(status["Self"])
        status["Self"]["AuthURL"] = "https://example.invalid/auth"
        d = self.tick(status, now=2.0)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "auth-url")
        self.assertNotIn("example.invalid", d.log or "")

    def test_state_inode_change_fails_closed_immediately(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "tailscaled.state")
        Path(path).write_bytes(b"x" * 2358)
        first = ident.state_stamp(path)
        self.assertEqual(first[1], 2358)
        self.tick(running(), now=1.0, stamp=first)
        # Replace the file so the inode changes, size stays the same.
        other = os.path.join(tmp, "other")
        Path(other).write_bytes(b"y" * 2358)
        os.replace(other, path)
        second = ident.state_stamp(path)
        self.assertNotEqual(second[0], first[0])
        d = self.tick(running(), now=2.0, stamp=second)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "state-changed")
        self.assertIn("inode", d.log)

    def test_state_size_change_fails_closed_as_regen(self):
        first = (7048947, 2358)
        self.tick(running(), now=1.0, stamp=first)
        d = self.tick(running(), now=2.0, stamp=(7048947, 4096))
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "state-changed")
        self.assertIn("size", d.log)

    def test_state_disappearance_after_a_stamp_fails_closed(self):
        self.tick(running(), now=1.0, stamp=(7048947, 2358))
        d = self.tick(running(), now=2.0, stamp=None)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "state-missing")

    def test_invisible_state_file_is_skipped(self):
        # Collector default: no visible state file, stamp stays None.
        d = self.tick(running(), now=1.0, stamp=None)
        self.assertFalse(d.fail_closed)
        self.assertIsNone(self.state.stamp)

    def test_blip_past_time_bound_fails_closed(self):
        self.tick(running(), now=1_000.0)
        d = self.tick(nostate_zeroed(), now=1_000.0)
        self.assertTrue(d.in_blip)
        self.assertFalse(d.fail_closed)
        d = self.tick(nostate_zeroed(), now=1_015.0)
        self.assertFalse(d.fail_closed)  # elapsed == 15, bound is strictly greater
        d = self.tick(nostate_zeroed(), now=1_015.1)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "blip-timeout")
        self.assertEqual(d.gap_reason, ident.GAP_IDENTITY)

    def test_blip_past_poll_bound_fails_closed(self):
        self.tick(running(), now=1.0)
        for i in range(3):
            d = ident.decide_identity(
                nostate_zeroed(), None, now=2.0 + i, state=self.state,
                blip_s=60, blip_polls=3,
            )
            self.assertFalse(d.fail_closed, "poll %s should still be in bound" % (i + 1))
        d = ident.decide_identity(
            nostate_zeroed(), None, now=10.0, state=self.state,
            blip_s=60, blip_polls=3,
        )
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "blip-timeout")

    def test_nonzero_key_change_during_a_blip_fails_closed_immediately(self):
        self.tick(running(KNOWN), now=1.0)
        self.tick(nostate_zeroed(), now=2.0)
        d = self.tick(starting(OTHER), now=2.5)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "nodekey-changed")


class IdentityLoopTests(unittest.TestCase):
    def test_loop_rides_out_the_20_10_blip_and_keeps_recording(self):
        tmp = tempfile.mkdtemp()
        conn = db.connect(os.path.join(tmp, "usage.sqlite"))
        conn.execute(
            """INSERT INTO kits(engine, tailscale_name, school, deployment_id, timezone,
               monitoring_enabled, last_pulled, note, created_at)
               VALUES ('idea03','idea03','dep','dep-idea03',NULL,1,NULL,'',?)""",
            (db.now_rfc3339(),),
        )
        conn.commit()
        api = FakeLocalAPI(tmp, running())
        key = os.path.join(tmp, "pull_key")
        Path(key).write_text("unused\n")
        flag = os.path.join(tmp, "restart-requested")
        env = {
            "DATA_DIR": tmp,
            "TS_SOCKET": api.path,
            "TS_RESTART_FLAG": flag,
            "PULL_KEY": key,
            "POLL_INTERVAL_S": "1",
            "UPLINK_INTERVAL_S": "1",
            "PULL_ONLINE_INTERVAL_S": "3600",
            "SIDECAR_RESTART_AFTER_S": "600",
            "SIDECAR_RESTART_MIN_INTERVAL_S": "600",
            "IDENTITY_BLIP_S": "15",
            "IDENTITY_BLIP_POLLS": "0",
            "IDENTITY_BLIP_POLL_S": "1",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        stop = threading.Event()
        # Hide any leftover TS_STATE_FILE from other tests.
        os.environ.pop("TS_STATE_FILE", None)
        try:
            thread = threading.Thread(
                target=mainmod.loop,
                kwargs={"conn": conn, "stop_event": stop, "pull_fn": lambda *_a, **_k: "success"},
                daemon=True,
            )
            thread.start()
            deadline = time.time() + 6
            while time.time() < deadline:
                n = conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0]
                if n > 0:
                    break
                time.sleep(0.05)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0], 0)
            # 20:10 sequence
            api.server.status = nostate_zeroed()
            time.sleep(0.4)
            api.server.status = starting()
            time.sleep(0.4)
            api.server.status = running()
            time.sleep(1.2)
            self.assertTrue(thread.is_alive())
            self.assertFalse(os.path.exists(flag))
            gaps = list(conn.execute("SELECT reason, end FROM collector_gaps"))
            identity_gaps = [g for g in gaps if g[0] in (ident.GAP_IDENTITY, ident.GAP_LOGGED_OUT)]
            self.assertEqual(identity_gaps, [])
            # After recovery the loop should still be closing sidecar-offline
            # (opened during the blip) and recording uplink.
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM uplink_samples").fetchone()[0], 0)
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

    def test_loop_does_not_request_restart_after_authurl(self):
        tmp = tempfile.mkdtemp()
        conn = db.connect(os.path.join(tmp, "usage.sqlite"))
        api = FakeLocalAPI(tmp, running())
        flag = os.path.join(tmp, "restart-requested")
        env = {
            "DATA_DIR": tmp,
            "TS_SOCKET": api.path,
            "TS_RESTART_FLAG": flag,
            "POLL_INTERVAL_S": "1",
            "IDENTITY_BLIP_S": "15",
            "SIDECAR_RESTART_AFTER_S": "1",
            "SIDECAR_RESTART_MIN_INTERVAL_S": "1",
        }
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        os.environ.pop("TS_STATE_FILE", None)
        stop = threading.Event()
        try:
            thread = threading.Thread(
                target=mainmod.loop,
                kwargs={"conn": conn, "stop_event": stop, "pull_fn": lambda *_a, **_k: "success"},
                daemon=True,
            )
            thread.start()
            time.sleep(0.4)
            bad = running()
            bad["AuthURL"] = "https://login.tailscale.com/a/not-a-real-login"
            api.server.status = bad
            time.sleep(1.5)
            self.assertTrue(thread.is_alive())
            self.assertFalse(os.path.exists(flag))
            reasons = [r[0] for r in conn.execute("SELECT reason FROM collector_gaps")]
            self.assertIn(ident.GAP_IDENTITY, reasons)
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
