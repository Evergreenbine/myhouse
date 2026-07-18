import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from fastapi import HTTPException

import local_db
from app.core import access_auth
from app.routers import user


class FamilyAuthTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "id": 7,
            "username": "xiaomei",
            "display_name": "小美",
            "role": "family",
            "is_active": True,
            "avatar": "data:image/jpeg;base64,test",
            "created_at": None,
            "updated_at": None,
            "last_login_at": None,
        }

    def test_password_hash_and_verify(self):
        password_hash, password_salt = access_auth.hash_password("family123")

        self.assertTrue(access_auth.verify_password("family123", password_hash, password_salt))
        self.assertFalse(access_auth.verify_password("wrong", password_hash, password_salt))

    def test_mysql_sql_translation_preserves_primary_key(self):
        sql = local_db._translate_mysql_sql("CREATE TABLE demo (id BIGINT PRIMARY KEY, key TEXT)")

        self.assertIn("PRIMARY KEY", sql)
        self.assertIn("`key` TEXT", sql)

    @patch("app.core.access_auth._jwt_secret", return_value="test-secret-at-least-32-characters-long")
    @patch("app.core.access_auth.db.get_family_account")
    def test_jwt_round_trip(self, get_family_account, _jwt_secret):
        get_family_account.return_value = self.account

        token = access_auth.issue_token(self.account)
        account = access_auth.decode_token(token)

        self.assertEqual(account["id"], 7)
        self.assertEqual(account["username"], "xiaomei")
        self.assertEqual(account["role"], "family")
        self.assertEqual(account["avatar"], "data:image/jpeg;base64,test")

    @patch("app.core.access_auth._jwt_secret", return_value="test-secret-at-least-32-characters-long")
    def test_tampered_jwt_is_rejected(self, _jwt_secret):
        token = access_auth.issue_token(self.account)

        self.assertIsNone(access_auth.decode_token(token + "changed"))

    @patch("app.core.access_auth._jwt_secret", return_value="test-secret-at-least-32-characters-long")
    def test_expired_jwt_is_rejected(self, _jwt_secret):
        token = jwt.encode(
            {"sub": "7", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            "test-secret-at-least-32-characters-long",
            algorithm="HS256",
        )

        self.assertIsNone(access_auth.decode_token(token))

    @patch("app.core.access_auth.db.touch_family_account_login")
    @patch("app.core.access_auth.db.get_family_account_by_username")
    def test_authenticate_active_account(self, get_by_username, touch_login):
        password_hash, password_salt = access_auth.hash_password("family123")
        get_by_username.return_value = {
            **self.account,
            "password_hash": password_hash,
            "password_salt": password_salt,
        }

        account = access_auth.authenticate("xiaomei", "family123")

        self.assertEqual(account["id"], 7)
        touch_login.assert_called_once_with(7)

    @patch("app.core.access_auth.db.create_family_account")
    @patch("app.core.access_auth.db.load_app_user", return_value={})
    @patch("app.core.access_auth.db.count_family_accounts", return_value=0)
    def test_bootstrap_creates_owner_account(self, _count, _load_config, create_account):
        with patch.object(access_auth.db, "DB_BACKEND", "mysql"):
            access_auth.ensure_owner_account()

        args = create_account.call_args.args
        self.assertEqual(args[0], "admin")
        self.assertEqual(args[1], "屋主")
        self.assertEqual(create_account.call_args.kwargs["role"], "owner")

    def test_family_account_cannot_manage_accounts(self):
        request = SimpleNamespace(state=SimpleNamespace(auth_user={"id": 7, "role": "family"}))

        with self.assertRaises(HTTPException) as raised:
            user._require_owner(request)

        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
