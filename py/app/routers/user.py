from typing import Any

from fastapi import APIRouter, Body

import local_db as db

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
        "user_nickname": _get("user_nickname", "主人"),
        "ai_avatar": _get("ai_avatar", "cat_icon.png"),
    }


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
def user_status():
    return {"password_set": False, "authenticated": True}


@router.post("/api/user/login")
def login(body: dict[str, Any] | None = Body(default=None)):
    return {"success": True}


@router.post("/api/user/logout")
def logout():
    return {"success": True}
