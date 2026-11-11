"""sidecar-wrap restart: bounded SIGTERM, then SIGCONT + SIGKILL."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAP = REPO / "collector" / "sidecar-wrap.sh"

HUNG_PY = """\
import signal
import sys
import time

log = sys.argv[1]


def rec(signum, _frame):
    with open(log, "a") as fh:
        fh.write("%d\\n" % signum)
        fh.flush()


signal.signal(signal.SIGTERM, rec)
signal.signal(signal.SIGCONT, rec)
while True:
    time.sleep(0.2)
"""


def _snapshot(path: Path):
    st = path.stat()
    return (st.st_ino, st.st_size, st.st_mtime_ns, path.read_bytes())


def _wait_text(path: Path, timeout: float = 8.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            text = path.read_text().strip()
            if text:
                return text
        time.sleep(0.05)
    raise AssertionError("timed out waiting for %s" % path)


def _comm(pid: int) -> str:
    return Path("/proc/%d/comm" % pid).read_text().strip()


def _alive(pid: int) -> bool:
    return Path("/proc/%d" % pid).exists()


class SidecarWrapRestartTests(unittest.TestCase):
    def _write_exec(self, path: Path, body: str) -> None:
        path.write_text(body)
        path.chmod(0o755)

    def _base_env(self, root: Path, boot: Path, term_s: str = "2", cont_s: str = "1"):
        state = root / "state"
        sockdir = root / "run"
        state.mkdir()
        sockdir.mkdir()
        state_file = state / "tailscaled.state"
        payload = '{"x": "PrivateNodeKey-present", "marker": "i414-sigkill-fixture"}'
        state_file.write_text(payload)
        env = os.environ.copy()
        env.pop("TS_AUTHKEY", None)
        env["TS_STATE_DIR"] = str(state)
        env["TS_SOCKET"] = str(sockdir / "tailscaled.sock")
        env["TS_SOCKET_DIR"] = str(sockdir)
        env["TS_RESTART_FLAG"] = str(sockdir / "restart-requested")
        env["TS_CONTAINERBOOT"] = str(boot)
        env["TS_RESTART_TERM_S"] = term_s
        env["TS_RESTART_CONT_S"] = cont_s
        return state_file, Path(env["TS_RESTART_FLAG"]), env

    def _stop(self, proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                proc.kill()
            proc.wait(timeout=5)

    def _hung_boot(self, root: Path) -> Path:
        ts_bin = root / "tailscaled"
        shutil.copy(sys.executable, ts_bin)
        script = root / "hung.py"
        script.write_text(HUNG_PY)
        sigs = root / "sigs.log"
        pidfile = root / "child.pid"
        count = root / "boot.count"
        boot = root / "fakeboot"
        self._write_exec(
            boot,
            "#!/bin/sh\n"
            "set -eu\n"
            f'ts="{ts_bin}"\n'
            f'py="{script}"\n'
            f'log="{sigs}"\n'
            f'pidfile="{pidfile}"\n'
            f'count="{count}"\n'
            '"$ts" "$py" "$log" &\n'
            "child=$!\n"
            'echo "$child" > "$pidfile"\n'
            "term() {\n"
            '  kill "$child" 2>/dev/null || true\n'
            '  wait "$child" 2>/dev/null || true\n'
            "  exit 0\n"
            "}\n"
            "trap term TERM\n"
            'echo started >> "$count"\n'
            'wait "$child" || true\n',
        )
        return boot

    def test_wrap_never_copies_moves_or_deletes_state_file(self):
        text = WRAP.read_text()
        self.assertNotRegex(text, r"\b(cp|mv|rm)\b[^\n]*tailscaled\.state")
        self.assertNotIn('rm -rf "$STATE"', text)
        self.assertNotIn("rm -rf $STATE", text)
        self.assertIn("sending SIGCONT then SIGKILL", text)
        self.assertIn("TS_RESTART_TERM_S", text)
        # Stale flag cleanup only; the persist file stays put.
        self.assertIn('rm -f "$STATE/restart-requested"', text)

    def test_identity_guard_still_fail_closed(self):
        sys.path.insert(0, str(REPO / "collector"))
        from src import identity as ident

        known = "1382c2eab7500ea4" + "a" * 48
        other = "abcdef0123456789" + "b" * 48
        state = ident.IdentityState()
        running = {
            "BackendState": "Running",
            "AuthURL": "",
            "Self": {"Online": True, "PublicKey": "nodekey:" + known},
        }
        now = 1000.0
        first = ident.decide_identity(running, None, now, state, blip_s=15, blip_polls=0)
        self.assertFalse(first.fail_closed)
        changed = dict(running)
        changed["Self"] = dict(running["Self"])
        changed["Self"]["PublicKey"] = "nodekey:" + other
        d = ident.decide_identity(changed, None, now + 1, state, blip_s=15, blip_polls=0)
        self.assertTrue(d.fail_closed)
        self.assertEqual(d.reason, "nodekey-changed")

        state2 = ident.IdentityState()
        ident.decide_identity(running, None, now, state2, blip_s=15, blip_polls=0)
        auth = dict(running)
        auth["AuthURL"] = "https://login.tailscale.com/a/not-a-real-login"
        d2 = ident.decide_identity(auth, None, now + 1, state2, blip_s=15, blip_polls=0)
        self.assertTrue(d2.fail_closed)

        state3 = ident.IdentityState()
        ident.decide_identity(running, None, now, state3, blip_s=15, blip_polls=0)
        login = dict(running)
        login["BackendState"] = "NeedsLogin"
        d3 = ident.decide_identity(login, None, now + 1, state3, blip_s=15, blip_polls=0)
        self.assertTrue(d3.fail_closed)

    def test_sigstop_child_escalates_to_sigkill_without_manual_sigcont(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = self._hung_boot(root)
            state_file, flag, env = self._base_env(root, boot, term_s="2", cont_s="1")
            before = _snapshot(state_file)
            log_path = root / "wrap.log"
            with open(log_path, "w") as log_fh:
                proc = subprocess.Popen(
                    ["sh", str(WRAP)],
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
            child = None
            used_safety_cont = False
            try:
                child = int(_wait_text(root / "child.pid"))
                self.assertEqual(_comm(child), "tailscaled")
                os.kill(child, signal.SIGSTOP)
                state = None
                stop_deadline = time.monotonic() + 2
                while time.monotonic() < stop_deadline:
                    stat = Path("/proc/%d/stat" % child).read_text()
                    rest = stat[stat.rfind(")") + 2 :]
                    state = rest.split()[0]
                    if state == "T":
                        break
                    time.sleep(0.05)
                self.assertEqual(state, "T")

                t0 = time.monotonic()
                flag.write_text("restart\n")
                deadline = t0 + 15
                while time.monotonic() < deadline:
                    if not _alive(child):
                        break
                    time.sleep(0.05)
                else:
                    try:
                        os.kill(child, signal.SIGCONT)
                        used_safety_cont = True
                    except ProcessLookupError:
                        pass
                    self.fail("child still alive after 15s; sent safety SIGCONT")

                elapsed = time.monotonic() - t0
                self.assertGreaterEqual(elapsed, 1.8)
                self.assertLess(elapsed, 12)
                self.assertFalse(used_safety_cont)

                # New boot should appear after wrap's 2s loop pause.
                new_deadline = time.monotonic() + 6
                new_child = None
                while time.monotonic() < new_deadline:
                    if (root / "child.pid").exists():
                        try:
                            cand = int((root / "child.pid").read_text().strip())
                        except ValueError:
                            cand = None
                        if cand and cand != child and _alive(cand):
                            new_child = cand
                            break
                    time.sleep(0.1)
                self.assertIsNotNone(new_child, "wrapper did not start a replacement boot")
                self.assertTrue(_alive(new_child))
                self.assertEqual(_comm(new_child), "tailscaled")

                logs = log_path.read_text()
                self.assertIn("restart requested by collector watchdog", logs)
                self.assertIn("sending SIGTERM to containerboot", logs)
                self.assertIn("sending SIGCONT then SIGKILL", logs)
                self.assertIn("sending SIGKILL to the containerboot process group", logs)
                sigs = (root / "sigs.log").read_text()
                self.assertIn(str(signal.SIGCONT), sigs)

                after = _snapshot(state_file)
                self.assertEqual(before, after)
                self.assertEqual(
                    state_file.read_text(),
                    '{"x": "PrivateNodeKey-present", "marker": "i414-sigkill-fixture"}',
                )
                self.assertGreaterEqual((root / "boot.count").read_text().count("started"), 2)
            finally:
                if used_safety_cont is False and child and _alive(child):
                    try:
                        os.kill(child, signal.SIGCONT)
                    except ProcessLookupError:
                        pass
                self._stop(proc)

    def test_graceful_sigterm_does_not_escalate_to_sigkill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "fakeboot"
            count = root / "boot.count"
            self._write_exec(
                boot,
                "#!/bin/sh\n"
                f'echo started >> "{count}"\n'
                "exec sleep 3600\n",
            )
            state_file, flag, env = self._base_env(root, boot, term_s="4", cont_s="1")
            before = _snapshot(state_file)
            log_path = root / "wrap.log"
            with open(log_path, "w") as log_fh:
                proc = subprocess.Popen(
                    ["sh", str(WRAP)],
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
            try:
                deadline = time.time() + 5
                while time.time() < deadline:
                    if count.exists() and count.read_text().count("started") >= 1:
                        break
                    time.sleep(0.05)
                else:
                    self.fail("boot did not start")
                t0 = time.monotonic()
                flag.write_text("restart\n")
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if count.exists() and count.read_text().count("started") >= 2:
                        break
                    time.sleep(0.05)
                else:
                    self.fail("wrapper did not restart a graceful boot")
                elapsed = time.monotonic() - t0
                # Detect (<=2s) + immediate SIGTERM + wrap's 2s loop pause.
                # Must not sit through the 4s TERM grace before restarting.
                self.assertLess(elapsed, 8)
                logs = log_path.read_text()
                self.assertIn("restart requested by collector watchdog", logs)
                self.assertIn("sending SIGTERM to containerboot", logs)
                self.assertNotIn("sending SIGKILL", logs)
                self.assertNotIn("sending SIGCONT then SIGKILL", logs)
                self.assertNotIn("still running after", logs)
                after = _snapshot(state_file)
                self.assertEqual(before, after)
            finally:
                self._stop(proc)


if __name__ == "__main__":
    unittest.main()
