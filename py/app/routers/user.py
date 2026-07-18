import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

import local_db as db
from app.core import access_auth

router = APIRouter()


def _user_config_response(local):
    def _get(key, default=""):
        return local.get(key, default)

    return {
        "api_key": _get("api_key", ""),
        "openai_key": _get("openai_key", ""),
        "zhipu_key": _get("zhipu_key", ""),
        "qwen_key": _get("qwen_key", ""),
        "custom_api_key": _get("custom_api_key", ""),
        "custom_base_url": _get("custom_base_url", ""),
        "custom_model": _get("custom_model", ""),
        "ai_provider": _get("ai_provider", ""),
        "ai_model": _get("ai_model", "deepseek-v4-flash"),
        "ocr_provider": _get("ocr_provider", "qwen"),
        "ocr_model": _get("ocr_model", "qwen-vl-max"),
        "ocr_key": _get("ocr_key", ""),
        "ai_persona": _get("ai_persona", "warm"),
        "ai_nickname": _get("ai_nickname", "哈基米"),
        "user_nickname": _get("user_nickname", "大王"),
        "ai_avatar": _get("ai_avatar", "/robot-avatar.jpg"),
    }


def _current_user(request: Request) -> dict[str, Any]:
    account = getattr(request.state, "auth_user", None)
    if not account:
        raise HTTPException(status_code=401, detail="请先登录")
    return account


def _require_owner(request: Request) -> dict[str, Any]:
    account = _current_user(request)
    if account.get("role") != "owner":
        raise HTTPException(status_code=403, detail="只有屋主可以管理家人账号")
    return account


def _clean_account_fields(body: dict[str, Any]) -> tuple[str, str, str]:
    username = str(body.get("username") or "").strip()
    display_name = str(body.get("display_name") or "").strip()
    password = str(body.get("password") or "")
    if not re.fullmatch(r"[\w.\-\u4e00-\u9fff]{2,32}", username):
        raise HTTPException(status_code=400, detail="账号需为2-32位，可使用中文、字母、数字、点、横线或下划线")
    if not display_name or len(display_name) > 20:
        raise HTTPException(status_code=400, detail="称呼需为1-20位")
    if len(password) < 6 or len(password) > 64:
        raise HTTPException(status_code=400, detail="密码需为6-64位")
    return username, display_name, password


def _validate_username_and_name(username: str, display_name: str) -> None:
    if not re.fullmatch(r"[\w.\-\u4e00-\u9fff]{2,32}", username):
        raise HTTPException(status_code=400, detail="账号需为2-32位，可使用中文、字母、数字、点、横线或下划线")
    if not display_name or len(display_name) > 20:
        raise HTTPException(status_code=400, detail="称呼需为1-20位")


def _validate_avatar(value: Any) -> str:
    avatar = str(value or "")
    if avatar and (not avatar.startswith("data:image/jpeg;base64,") or len(avatar) > 100000):
        raise HTTPException(status_code=400, detail="头像格式或大小不正确")
    return avatar


@router.get("/api/user/config")
def get_user_config():
    local = db.load_app_user()
    if local:
        return _user_config_response(local)
    return {}


@router.post("/api/user/config")
def save_user_config(body: dict[str, Any] | None = Body(default=None)):
    db.save_app_user(body or {})
    return {"success": True}


@router.get("/api/user/status")
def user_status(request: Request):
    account = access_auth.decode_token(access_auth.token_from_headers(request.headers))
    return {
        "authenticated": bool(account),
        "user": account,
        "login_only": True,
    }


@router.post("/api/user/login")
def login(body: dict[str, Any] | None = Body(default=None)):
    body = body or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    account = access_auth.authenticate(username, password)
    if not account:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return {
        "success": True,
        "access_token": access_auth.issue_token(account),
        "token_type": "bearer",
        "expires_in": access_auth.JWT_EXPIRE_HOURS * 3600,
        "user": access_auth.public_account(account),
    }


@router.post("/api/user/logout")
def logout():
    return {"success": True}


@router.patch("/api/user/profile")
def update_my_profile(request: Request, body: dict[str, Any] | None = Body(default=None)):
    current = _current_user(request)
    account = db.get_family_account(current["id"])
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    body = body or {}
    username = str(body.get("username", account.get("username") or "")).strip()
    display_name = str(body.get("display_name", account.get("display_name") or "")).strip()
    _validate_username_and_name(username, display_name)
    existing = db.get_family_account_by_username(username)
    if existing and int(existing["id"]) != int(account["id"]):
        raise HTTPException(status_code=409, detail="该登录账号已存在")
    avatar = _validate_avatar(body.get("avatar", account.get("avatar") or ""))
    new_password = str(body.get("new_password") or "")
    if new_password:
        current_password = str(body.get("current_password") or "")
        if not access_auth.verify_password(current_password, account.get("password_hash", ""), account.get("password_salt", "")):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        if len(new_password) < 6 or len(new_password) > 64:
            raise HTTPException(status_code=400, detail="新密码需为6-64位")
    account = db.update_family_account_identity(account["id"], username, display_name)
    account = db.update_family_account_avatar(account["id"], avatar)
    if new_password:
        password_hash, password_salt = access_auth.hash_password(new_password)
        db.update_family_account_password(account["id"], password_hash, password_salt)
        account = db.get_family_account(account["id"])
    return {"success": True, "user": access_auth.public_account(account)}


@router.get("/api/user/accounts")
def list_accounts(request: Request):
    _require_owner(request)
    return {"items": [access_auth.public_account(item) for item in db.list_family_accounts()]}


@router.post("/api/user/accounts")
def create_account(request: Request, body: dict[str, Any] | None = Body(default=None)):
    _require_owner(request)
    username, display_name, password = _clean_account_fields(body or {})
    if db.get_family_account_by_username(username):
        raise HTTPException(status_code=409, detail="该登录账号已存在")
    password_hash, password_salt = access_auth.hash_password(password)
    account = db.create_family_account(username, display_name, password_hash, password_salt, role="family")
    return {"success": True, "account": access_auth.public_account(account)}


@router.patch("/api/user/accounts/{account_id}")
def update_account(account_id: int, request: Request, body: dict[str, Any] | None = Body(default=None)):
    current = _require_owner(request)
    account = db.get_family_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    body = body or {}
    display_name = str(body.get("display_name", account.get("display_name") or "")).strip()
    if not display_name or len(display_name) > 20:
        raise HTTPException(status_code=400, detail="称呼需为1-20位")
    is_active = bool(body.get("is_active", account.get("is_active")))
    if account.get("role") == "owner" and not is_active:
        raise HTTPException(status_code=400, detail="屋主账号不能停用")
    if int(current["id"]) == account_id and not is_active:
        raise HTTPException(status_code=400, detail="不能停用当前账号")
    avatar = None
    if "avatar" in body:
        avatar = _validate_avatar(body.get("avatar"))
    account = db.update_family_account_profile(account_id, display_name, is_active)
    if avatar is not None:
        account = db.update_family_account_avatar(account_id, avatar)
    return {"success": True, "account": access_auth.public_account(account)}


@router.post("/api/user/accounts/{account_id}/password")
def reset_account_password(account_id: int, request: Request, body: dict[str, Any] | None = Body(default=None)):
    _require_owner(request)
    account = db.get_family_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    password = str((body or {}).get("password") or "")
    if len(password) < 6 or len(password) > 64:
        raise HTTPException(status_code=400, detail="密码需为6-64位")
    password_hash, password_salt = access_auth.hash_password(password)
    db.update_family_account_password(account_id, password_hash, password_salt)
    return {"success": True}


@router.delete("/api/user/accounts/{account_id}")
def delete_account(account_id: int, request: Request):
    current = _require_owner(request)
    account = db.get_family_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    if account.get("role") == "owner" or int(current["id"]) == account_id:
        raise HTTPException(status_code=400, detail="屋主账号不能删除")
    db.delete_family_account(account_id)
    return {"success": True}
