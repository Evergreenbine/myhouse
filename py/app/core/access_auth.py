import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

import local_db as db


PASSWORD_HASH_KEY = "access_password_hash"
PASSWORD_SALT_KEY = "access_password_salt"
JWT_SECRET_KEY = "access_jwt_secret"
HASH_ITERATIONS = 180000
DEFAULT_ACCESS_USERNAME = os.environ.get("DEFAULT_ACCESS_USERNAME", "admin")
DEFAULT_ACCESS_PASSWORD = os.environ.get("DEFAULT_ACCESS_PASSWORD", "fudada1688.")
DEFAULT_ACCESS_NAME = os.environ.get("DEFAULT_ACCESS_NAME", "屋主")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.environ.get("JWT_EXPIRE_HOURS", "168"))


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS,
    ).hex()


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return _hash_password(password, salt), salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    if not password or not password_hash or not password_salt:
        return False
    candidate = _hash_password(password, password_salt)
    return hmac.compare_digest(password_hash, candidate)


def ensure_owner_account() -> None:
    if db.DB_BACKEND != "mysql" or db.count_family_accounts() > 0:
        return
    legacy = db.load_app_user() or {}
    password_hash = str(legacy.get(PASSWORD_HASH_KEY) or "")
    password_salt = str(legacy.get(PASSWORD_SALT_KEY) or "")
    if not password_hash or not password_salt:
        password_hash, password_salt = hash_password(DEFAULT_ACCESS_PASSWORD)
    db.create_family_account(
        DEFAULT_ACCESS_USERNAME,
        DEFAULT_ACCESS_NAME,
        password_hash,
        password_salt,
        role="owner",
    )


def _jwt_secret() -> str:
    configured = os.environ.get("JWT_SECRET", "").strip()
    if configured:
        return configured
    config = db.load_app_user() or {}
    stored = str(config.get(JWT_SECRET_KEY) or "").strip()
    if stored:
        return stored
    secret = secrets.token_urlsafe(48)
    db.save_app_user({JWT_SECRET_KEY: secret})
    return secret


def public_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(account.get("id") or 0),
        "username": str(account.get("username") or ""),
        "display_name": str(account.get("display_name") or ""),
        "role": str(account.get("role") or "family"),
        "is_active": bool(account.get("is_active")),
        "avatar": str(account.get("avatar") or ""),
        "created_at": account.get("created_at"),
        "updated_at": account.get("updated_at"),
        "last_login_at": account.get("last_login_at"),
    }


def issue_token(account: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(account["id"]),
        "username": account["username"],
        "display_name": account.get("display_name") or account["username"],
        "role": account.get("role") or "family",
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    account = db.get_family_account_by_username(username)
    if not account or not account.get("is_active"):
        return None
    if not verify_password(password, account.get("password_hash", ""), account.get("password_salt", "")):
        return None
    db.touch_family_account_login(account["id"])
    return account


def decode_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        account_id = int(payload.get("sub") or 0)
    except (jwt.PyJWTError, TypeError, ValueError):
        return None
    account = db.get_family_account(account_id)
    if not account or not account.get("is_active"):
        return None
    return public_account(account)


def token_from_headers(headers: Any) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""
