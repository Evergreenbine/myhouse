import hashlib
import hmac
import json
import secrets
from typing import Any

import local_db as db


PASSWORD_HASH_KEY = "access_password_hash"
PASSWORD_SALT_KEY = "access_password_salt"
SESSIONS_KEY = "access_sessions"
HASH_ITERATIONS = 180000
DEFAULT_ACCESS_PASSWORD = "fudada1688."


def _load_cfg() -> dict[str, str]:
    return db.load_app_user()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS,
    ).hex()


def password_is_set() -> bool:
    return bool(_load_cfg().get(PASSWORD_HASH_KEY))


def verify_password(password: str) -> bool:
    cfg = _load_cfg()
    stored = cfg.get(PASSWORD_HASH_KEY, "")
    salt = cfg.get(PASSWORD_SALT_KEY, "")
    if not stored or not salt or not password:
        return False
    return hmac.compare_digest(stored, _hash_password(password, salt))


def _load_sessions(cfg: dict[str, str] | None = None) -> list[str]:
    raw = (cfg or _load_cfg()).get(SESSIONS_KEY, "[]")
    try:
        sessions = json.loads(raw)
    except Exception:
        return []
    if not isinstance(sessions, list):
        return []
    return [s for s in sessions if isinstance(s, str) and s]


def issue_token() -> str:
    token = secrets.token_urlsafe(32)
    cfg = _load_cfg()
    sessions = _load_sessions(cfg)
    sessions.append(token)
    sessions = sessions[-20:]
    db.save_app_user({SESSIONS_KEY: json.dumps(sessions)})
    return token


def validate_token(token: str | None) -> bool:
    if not password_is_set():
        return False
    if not token:
        return False
    return token in _load_sessions()


def revoke_token(token: str | None) -> None:
    if not token:
        return
    sessions = [s for s in _load_sessions() if s != token]
    db.save_app_user({SESSIONS_KEY: json.dumps(sessions)})


def set_password(new_password: str) -> str:
    salt = secrets.token_hex(16)
    db.save_app_user({
        PASSWORD_SALT_KEY: salt,
        PASSWORD_HASH_KEY: _hash_password(new_password, salt),
        SESSIONS_KEY: "[]",
    })
    return issue_token()


def ensure_default_password() -> None:
    if DEFAULT_ACCESS_PASSWORD and not verify_password(DEFAULT_ACCESS_PASSWORD):
        salt = secrets.token_hex(16)
        db.save_app_user({
            PASSWORD_SALT_KEY: salt,
            PASSWORD_HASH_KEY: _hash_password(DEFAULT_ACCESS_PASSWORD, salt),
            SESSIONS_KEY: "[]",
        })


def token_from_headers(headers: Any) -> str:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-myhouse-token", "").strip()
