import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    X25519PrivateKey = None
    HAS_CRYPTO = False

REPO = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO / "collector"))

from src.nodekey import compare, disk_nodekeys, public_from_private_hex, x25519  # noqa: E402

# RFC 7748 §6.1
RFC_PRIV = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
RFC_PUB = "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"

CHECK = REPO / "script" / "check-idea-hub-nodekey.py"
JOIN = REPO / "script" / "join-idea-hub-once.sh"
WRAP = REPO / "collector" / "sidecar-wrap.sh"
# Built at runtime so the file never contains a tskey-<type>-<id> literal
# (GitHub secret scanning flags those even in fixtures).
FAKE_AUTHKEY = "tsk" + "ey-auth-" + "FAKE" * 4 + "-not-real"



def _keypair():
    if HAS_CRYPTO:
        priv = os.urandom(32)
        pub = X25519PrivateKey.from_private_bytes(priv).public_key().public_bytes_raw().hex()
        return priv, pub
    return RFC_PRIV, RFC_PUB


def _state_file(dirpath: Path, priv: bytes):
    inner = json.dumps({"Config": {"PrivateNodeKey": "privkey:" + priv.hex()}})
    import base64
    encoded = base64.b64encode(inner.encode()).decode()
    (dirpath / "tailscaled.state").write_text(json.dumps({"profile-test": encoded}))


class NodekeyTests(unittest.TestCase):
    def test_x25519_rfc7748_vector(self):
        nine = (9).to_bytes(32, "little")
        self.assertEqual(x25519(RFC_PRIV, nine).hex(), RFC_PUB)
        self.assertEqual(public_from_private_hex(RFC_PRIV.hex()), RFC_PUB)

    def test_x25519_matches_cryptography(self):
        if not HAS_CRYPTO:
            self.skipTest("cryptography not installed")
        priv, pub = _keypair()
        nine = (9).to_bytes(32, "little")
        self.assertEqual(x25519(priv, nine).hex(), pub)
        self.assertEqual(public_from_private_hex(priv.hex()), pub)

    def test_disk_nodekeys_and_compare(self):
        priv, pub = _keypair()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state_file(root, priv)
            pubs = disk_nodekeys(root / "tailscaled.state")
            self.assertEqual(len(pubs), 1)
            self.assertEqual(pubs[0][1], pub)
            matched = compare(pubs, "nodekey:" + pub)
            self.assertTrue(matched["match"])
            self.assertEqual(matched["status_prefix"], pub[:16])
            other = compare(pubs, "nodekey:" + ("ab" * 32))
            self.assertFalse(other["match"])

    def test_check_script_match_and_mismatch(self):
        priv, pub = _keypair()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state_file(root, priv)
            status = root / "status.json"
            status.write_text(json.dumps({"BackendState": "Running", "Self": {"PublicKey": "nodekey:" + pub}}))
            ok = subprocess.run(
                ["python3", str(CHECK), "--state-dir", str(root), "--status-json", str(status)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("match=true", ok.stdout)
            self.assertNotIn(priv.hex(), ok.stdout + ok.stderr)
            status.write_text(json.dumps({"BackendState": "Running", "Self": {"PublicKey": "nodekey:" + ("cd" * 32)}}))
            bad = subprocess.run(
                ["python3", str(CHECK), "--state-dir", str(root), "--status-json", str(status)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
            self.assertIn("match=false", bad.stdout)
            self.assertNotIn(priv.hex(), bad.stdout + bad.stderr)


class SidecarWrapGuardTests(unittest.TestCase):
    def test_refuses_empty_state_without_authkey(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("TS_AUTHKEY", None)
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("refusing to start", result.stderr)
            self.assertNotIn("tskey-", result.stderr + result.stdout)

    def test_allows_empty_state_with_authkey(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["TS_AUTHKEY"] = FAKE_AUTHKEY
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(FAKE_AUTHKEY, result.stdout + result.stderr)

    def test_allows_state_with_nodekey(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tailscaled.state").write_text('{"x": "PrivateNodeKey-present"}')
            env = os.environ.copy()
            env.pop("TS_AUTHKEY", None)
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_allows_encoded_persist_profile_without_plaintext_field(self):
        priv, _pub = _keypair()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _state_file(root, priv)
            text = (root / "tailscaled.state").read_text()
            self.assertNotIn("PrivateNodeKey", text)
            env = os.environ.copy()
            env.pop("TS_AUTHKEY", None)
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(priv.hex(), result.stdout + result.stderr)
            self.assertNotIn("tskey-", result.stdout + result.stderr)

    def test_refuses_small_state_without_nodekey(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tailscaled.state").write_text('{"_machinekey": "' + ("ab" * 40) + '"}')
            env = os.environ.copy()
            env.pop("TS_AUTHKEY", None)
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("refusing to start", result.stderr)
            self.assertLess((Path(tmp) / "tailscaled.state").stat().st_size, 200)

    def test_size_fallback_allows_large_state_without_python(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tailscaled.state").write_bytes(b"n" * 250)
            bindir = root / "bin"
            bindir.mkdir()
            for name in ("grep", "wc", "tr"):
                src = shutil.which(name)
                self.assertIsNotNone(src, name)
                os.symlink(src, bindir / name)
            env = os.environ.copy()
            env.pop("TS_AUTHKEY", None)
            env["PATH"] = str(bindir)
            result = subprocess.run(
                ["/bin/sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_refuses_keyed_start_when_marker_present(self):
        fake = FAKE_AUTHKEY
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "authkey-join-blocked").write_text("blocked\n")
            env = os.environ.copy()
            env["TS_AUTHKEY"] = fake
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("authkey-join-blocked", result.stderr)
            self.assertNotIn(fake, result.stdout + result.stderr)

    def test_allows_nodekey_even_when_marker_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "tailscaled.state").write_text('{"x": "PrivateNodeKey-present"}')
            (Path(tmp) / "authkey-join-blocked").write_text("blocked\n")
            env = os.environ.copy()
            env.pop("TS_AUTHKEY", None)
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


class SidecarWrapOneJoinTests(unittest.TestCase):
    def _env(self, tmp, auth=True):
        env = os.environ.copy()
        if auth:
            env["TS_AUTHKEY"] = FAKE_AUTHKEY
        else:
            env.pop("TS_AUTHKEY", None)
        env["TS_STATE_DIR"] = str(tmp)
        env["TS_JOIN_TIMEOUT"] = "2"
        return env

    def _write_exec(self, path: Path, body: str):
        path.write_text(body)
        path.chmod(0o755)

    def _fake_tailscale(self, root: Path, running: bool = False) -> Path:
        path = root / "fake-tailscale"
        if running:
            body = (
                "#!/bin/sh\n"
                "cat <<'JSON'\n"
                '{"BackendState":"Running","Self":{"Online":true,"TailscaleIPs":["100.64.0.1"]}}\n'
                "JSON\n"
            )
        else:
            body = "#!/bin/sh\nexit 1\n"
        self._write_exec(path, body)
        return path

    def test_failed_join_writes_marker_and_does_not_retry(self):
        fake = FAKE_AUTHKEY
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            count = root / "boot.count"
            boot = root / "fakeboot"
            self._write_exec(
                boot,
                "#!/bin/sh\n"
                f'echo x >> "{count}"\n'
                "exit 1\n",
            )
            env = self._env(root)
            env["TS_AUTHKEY"] = fake
            env["TS_CONTAINERBOOT"] = str(boot)
            env["TS_TAILSCALE"] = str(self._fake_tailscale(root, running=False))
            result = subprocess.run(
                ["sh", str(WRAP)],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(count.read_text().count("x"), 1, count.read_text())
            marker = root / "authkey-join-blocked"
            self.assertTrue(marker.is_file(), result.stderr)
            marker_text = marker.read_text()
            self.assertIn("authkey-join-blocked", marker_text)
            self.assertNotIn(fake, marker_text)
            self.assertNotIn(fake, result.stdout + result.stderr)
            # A second start with the same key must refuse without running boot again.
            again = subprocess.run(
                ["sh", str(WRAP), "--check-state", str(root)],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(again.returncode, 1)
            self.assertIn("authkey-join-blocked", again.stderr)
            self.assertEqual(count.read_text().count("x"), 1)

    def test_join_timeout_writes_marker_and_stops_boot(self):
        fake = FAKE_AUTHKEY
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            count = root / "boot.count"
            boot = root / "fakeboot"
            self._write_exec(
                boot,
                "#!/bin/sh\n"
                f'echo x >> "{count}"\n'
                "exec sleep 60\n",
            )
            env = self._env(root)
            env["TS_AUTHKEY"] = fake
            env["TS_CONTAINERBOOT"] = str(boot)
            env["TS_JOIN_TIMEOUT"] = "2"
            env["TS_TAILSCALE"] = str(self._fake_tailscale(root, running=False))
            result = subprocess.run(
                ["sh", str(WRAP)],
                capture_output=True,
                text=True,
                env=env,
                timeout=20,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(count.read_text().count("x"), 1)
            self.assertTrue((root / "authkey-join-blocked").is_file())
            self.assertIn("timed out", result.stderr)
            self.assertNotIn(fake, result.stdout + result.stderr)

    def test_successful_join_does_not_write_marker_or_reinvoke_boot(self):
        fake = FAKE_AUTHKEY
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            self._write_exec(
                bindir / "tailscale",
                "#!/bin/sh\n"
                'cat <<\'JSON\'\n'
                '{"BackendState":"Running","Self":{"Online":true,"TailscaleIPs":["100.64.0.1"]}}\n'
                "JSON\n",
            )
            count = root / "boot.count"
            boot = root / "fakeboot"
            state = root / "tailscaled.state"
            self._write_exec(
                boot,
                "#!/bin/sh\n"
                f'echo x >> "{count}"\n'
                f"echo '{{\"x\": \"PrivateNodeKey\"}}' > '{state}'\n"
                "exec sleep 60\n",
            )
            env = self._env(root)
            env["TS_AUTHKEY"] = fake
            env["TS_CONTAINERBOOT"] = str(boot)
            env["TS_TAILSCALE"] = str(bindir / "tailscale")
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            proc = subprocess.Popen(
                ["sh", str(WRAP)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )
            try:
                deadline = 8
                import time
                started = time.time()
                while time.time() - started < deadline:
                    if state.exists() and "PrivateNodeKey" in state.read_text():
                        break
                    if proc.poll() is not None:
                        out, err = proc.communicate()
                        self.fail(f"wrapper exited early rc={proc.returncode}: {out}{err}")
                    time.sleep(0.2)
                else:
                    proc.kill()
                    out, err = proc.communicate()
                    self.fail(f"state not written in time: {out}{err}")
                time.sleep(1.2)
                self.assertIsNone(proc.poll(), "wrapper should keep running after a successful join")
                self.assertFalse((root / "authkey-join-blocked").exists())
                self.assertEqual(count.read_text().count("x"), 1)
            finally:
                if proc.poll() is None:
                    try:
                        os.killpg(proc.pid, 15)
                    except ProcessLookupError:
                        proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, 9)
                        except ProcessLookupError:
                            proc.kill()
                        proc.wait(timeout=5)
                try:
                    out, err = proc.communicate(timeout=2)
                except Exception:
                    out, err = "", ""
                combined = (out or "") + (err or "")
                self.assertNotIn(fake, combined)


class JoinOnceTests(unittest.TestCase):
    def test_write_and_remove_env_without_printing_key(self):
        fake = FAKE_AUTHKEY
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("port=58546\n")
            env = os.environ.copy()
            env["TS_AUTHKEY"] = fake
            wrote = subprocess.run(
                ["sh", str(JOIN), "write-env", "--env-file", str(env_file)],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(wrote.returncode, 0, wrote.stderr)
            self.assertNotIn(fake, wrote.stdout + wrote.stderr)
            text = env_file.read_text()
            self.assertIn("TS_AUTHKEY=" + fake, text)
            self.assertIn("port=58546", text)
            removed = subprocess.run(
                ["sh", str(JOIN), "remove-env", "--env-file", str(env_file)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            after = env_file.read_text()
            self.assertNotIn("TS_AUTHKEY=", after)
            self.assertIn("port=58546", after)
            self.assertNotIn(fake, removed.stdout + removed.stderr)

    def test_attempt_removes_env_after_success_and_failure(self):
        fake = FAKE_AUTHKEY
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("port=58546\n")
            env = os.environ.copy()
            env["TS_AUTHKEY"] = fake
            # Command sees the key in the file, then exits 0; attempt must strip it.
            ok = subprocess.run(
                [
                    "sh",
                    str(JOIN),
                    "attempt",
                    "--env-file",
                    str(env_file),
                    "--",
                    "sh",
                    "-c",
                    'grep -q "^TS_AUTHKEY=" "$1" && test -n "$TS_AUTHKEY"',
                    "check",
                    str(env_file),
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertNotIn(fake, ok.stdout + ok.stderr)
            self.assertNotIn("TS_AUTHKEY=", env_file.read_text())
            self.assertIn("port=58546", env_file.read_text())

            env_file.write_text("port=58546\n")
            bad = subprocess.run(
                [
                    "sh",
                    str(JOIN),
                    "attempt",
                    "--env-file",
                    str(env_file),
                    "--",
                    "sh",
                    "-c",
                    "exit 7",
                ],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(bad.returncode, 7, bad.stdout + bad.stderr)
            self.assertNotIn(fake, bad.stdout + bad.stderr)
            self.assertNotIn("TS_AUTHKEY=", env_file.read_text())
            self.assertIn("port=58546", env_file.read_text())

    def test_runbook_documents_one_attempt_and_tag_owners(self):
        text = (REPO / "docs" / "runbook.md").read_text()
        self.assertIn("authkey-join-blocked", text)
        self.assertIn("tagOwners", text)
        self.assertIn("burned", text)
        self.assertIn("tag:idea-hub", text)
        self.assertIn("ticked", text)
        self.assertIn("attempt", text)
        wrap = WRAP.read_text()
        self.assertIn("authkey-join-blocked", wrap)
        self.assertIn("keyed_join_once", wrap)


if __name__ == "__main__":
    unittest.main()
