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
            env["TS_AUTHKEY"] = "tskey-auth-TESTONLY-not-real"
            result = subprocess.run(
                ["sh", str(WRAP), "--check-state", tmp],
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("tskey-auth-TESTONLY-not-real", result.stdout + result.stderr)

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


class JoinOnceTests(unittest.TestCase):
    def test_write_and_remove_env_without_printing_key(self):
        fake = "tskey-auth-TESTONLY-not-real"
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


if __name__ == "__main__":
    unittest.main()
