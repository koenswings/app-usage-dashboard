"""U-9 operator accounts: exactly koen and marco, hashed at rest."""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))

from src import auth


class OperatorAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "operators.json")
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "IDEA_USAGE_OPERATORS_FILE",
                "IDEA_USAGE_KOEN_PASSWORD",
                "IDEA_USAGE_MARCO_PASSWORD",
                "IDEA_USAGE_ADMIN_PASSWORD",
                "IDEA_USAGE_OPERATORS",
                "IDEA_USAGE_PBKDF2_ITERATIONS",
                "IDEA_USAGE_SESSION_SECRET",
            )
        }
        os.environ["IDEA_USAGE_OPERATORS_FILE"] = self.path
        os.environ["IDEA_USAGE_KOEN_PASSWORD"] = "koen911!"
        os.environ["IDEA_USAGE_MARCO_PASSWORD"] = "marco911!"
        os.environ["IDEA_USAGE_PBKDF2_ITERATIONS"] = "1000"
        os.environ["IDEA_USAGE_SESSION_SECRET"] = "test-secret"
        os.environ.pop("IDEA_USAGE_ADMIN_PASSWORD", None)
        os.environ.pop("IDEA_USAGE_OPERATORS", None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_first_run_seeds_only_koen_and_marco(self):
        stored = auth.ensure_operators()
        self.assertEqual(set(stored), {"koen", "marco"})
        self.assertTrue(os.path.isfile(self.path))
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)
        raw = Path(self.path).read_text(encoding="utf-8")
        data = json.loads(raw)
        self.assertEqual(data["schema"], "idea-usage-operators/1")
        self.assertEqual(set(data["operators"]), {"koen", "marco"})
        self.assertNotIn("koen911!", raw)
        self.assertNotIn("marco911!", raw)
        self.assertTrue(raw.count("pbkdf2_sha256$") >= 2)
        self.assertTrue(auth.check_credentials("koen", "koen911!"))
        self.assertTrue(auth.check_credentials("marco", "marco911!"))
        self.assertFalse(auth.check_credentials("admin", "admin911!"))
        self.assertFalse(auth.check_credentials("koen", "wrong"))

    def test_legacy_admin_env_does_not_create_an_account(self):
        os.environ["IDEA_USAGE_ADMIN_PASSWORD"] = "admin911!"
        os.environ["IDEA_USAGE_OPERATORS"] = "alice:secret,bob:other"
        auth.ensure_operators()
        self.assertFalse(auth.check_credentials("admin", "admin911!"))
        self.assertFalse(auth.check_credentials("alice", "secret"))
        self.assertFalse(auth.check_credentials("bob", "other"))
        self.assertTrue(auth.check_credentials("koen", "koen911!"))

    def test_existing_file_drops_other_accounts_and_rehashes_plaintext(self):
        Path(self.path).write_text(
            json.dumps({"admin": "admin911!", "koen": "custom-plain"}),
            encoding="utf-8",
        )
        auth.ensure_operators()
        raw = Path(self.path).read_text(encoding="utf-8")
        self.assertNotIn("custom-plain", raw)
        self.assertNotIn("admin911!", raw)
        self.assertNotIn("marco911!", raw)
        data = json.loads(raw)
        self.assertEqual(set(data["operators"]), {"koen", "marco"})
        self.assertTrue(auth.check_credentials("koen", "custom-plain"))
        self.assertTrue(auth.check_credentials("marco", "marco911!"))
        self.assertFalse(auth.check_credentials("admin", "admin911!"))

    def test_changed_password_survives_restart_and_is_not_reset_from_env(self):
        auth.ensure_operators()
        auth.change_password("koen", "koen911!", "newpass99")
        self.assertTrue(auth.check_credentials("koen", "newpass99"))
        self.assertFalse(auth.check_credentials("koen", "koen911!"))
        raw = Path(self.path).read_text(encoding="utf-8")
        self.assertNotIn("newpass99", raw)
        self.assertNotIn("koen911!", raw)
        auth.ensure_operators()
        self.assertTrue(auth.check_credentials("koen", "newpass99"))
        self.assertFalse(auth.check_credentials("koen", "koen911!"))
        self.assertTrue(auth.check_credentials("marco", "marco911!"))

    def test_missing_seed_env_names_the_variable_not_the_password(self):
        os.environ.pop("IDEA_USAGE_MARCO_PASSWORD")
        with self.assertRaises(RuntimeError) as ctx:
            auth.ensure_operators()
        message = str(ctx.exception)
        self.assertIn("IDEA_USAGE_MARCO_PASSWORD", message)
        self.assertNotIn("marco911!", message)
        self.assertNotIn("koen911!", message)

    def test_change_password_rejects_wrong_current_and_short_new(self):
        auth.ensure_operators()
        with self.assertRaises(auth.PasswordError) as ctx:
            auth.change_password("koen", "nope", "newpass99")
        self.assertEqual(ctx.exception.code, "unauthorized")
        with self.assertRaises(auth.PasswordError) as ctx:
            auth.change_password("koen", "koen911!", "short")
        self.assertEqual(ctx.exception.code, "validation")
        self.assertTrue(auth.check_credentials("koen", "koen911!"))

    def test_admin_session_token_is_rejected(self):
        token = auth.mint_token("admin")
        self.assertIsNone(auth.read_token(token))
        self.assertEqual(auth.read_token(auth.mint_token("koen")), "koen")
        self.assertEqual(auth.read_token(auth.mint_token("marco")), "marco")

    def test_seed_error_does_not_print_passwords(self):
        # Defence-in-depth: the RuntimeError text itself is what would land in logs.
        os.environ["IDEA_USAGE_KOEN_PASSWORD"] = "super-secret-seed"
        os.environ.pop("IDEA_USAGE_MARCO_PASSWORD")
        with self.assertRaises(RuntimeError) as ctx:
            auth.ensure_operators()
        self.assertNotIn("super-secret-seed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
