# -*- coding: utf-8 -*-
"""AI session state storage backed by Redis and MySQL."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import local_db as db


STATE_TTL_SECONDS = int(os.getenv("MYHOUSE_AI_STATE_TTL_SECONDS", "172800"))
TRACE_TTL_SECONDS = int(os.getenv("MYHOUSE_AI_TRACE_TTL_SECONDS", "172800"))
REDIS_URL = os.getenv("MYHOUSE_REDIS_URL") or os.getenv("REDIS_URL") or ""

_REDIS_CLIENT = None
_REDIS_ERROR = ""


def _safe_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _get_redis():
    global _REDIS_CLIENT, _REDIS_ERROR
    if not REDIS_URL:
        return None
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    try:
        import redis

        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        _REDIS_ERROR = ""
        return client
    except Exception as exc:
        _REDIS_ERROR = str(exc)
        _REDIS_CLIENT = None
        return None


def _state_key(thread_id: str) -> str:
    return f"myhouse:ai:state:{thread_id}"


def _trace_key(thread_id: str) -> str:
    return f"myhouse:ai:trace:{thread_id}"


def load_thread_state(thread_id: str) -> Dict[str, Any]:
    if not thread_id:
        return {}
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(_state_key(thread_id))
            if raw:
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    return payload
        except Exception:
            pass
    try:
        state = db.load_ai_thread_state(thread_id)
        if state:
            save_thread_state(thread_id, state)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def save_thread_state(thread_id: str, state: Dict[str, Any]) -> bool:
    if not thread_id:
        return False
    payload = state if isinstance(state, dict) else {}
    try:
        db.save_ai_thread_state(thread_id, payload)
    except Exception:
        pass
    client = _get_redis()
    if client is not None:
        try:
            client.set(_state_key(thread_id), _safe_json(payload), ex=STATE_TTL_SECONDS)
        except Exception:
            pass
    return True


def append_trace(thread_id: str, event: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    data = payload if isinstance(payload, dict) else {}
    try:
        db.append_ai_trace(thread_id, event, data)
    except Exception:
        pass
    client = _get_redis()
    if client is not None and thread_id:
        try:
            client.rpush(_trace_key(thread_id), _safe_json({
                "event": str(event or ""),
                "payload": data,
            }))
            client.ltrim(_trace_key(thread_id), -80, -1)
            client.expire(_trace_key(thread_id), TRACE_TTL_SECONDS)
        except Exception:
            pass
    return True


def load_trace(thread_id: str, limit: int = 80) -> List[Dict[str, Any]]:
    client = _get_redis()
    if client is not None and thread_id:
        try:
            values = client.lrange(_trace_key(thread_id), max(-int(limit or 80), -80), -1)
            items: List[Dict[str, Any]] = []
            for idx, raw in enumerate(values):
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {}
                if isinstance(data, dict):
                    items.append({
                        "id": idx,
                        "thread_id": thread_id,
                        "event": data.get("event"),
                        "payload": data.get("payload") if isinstance(data.get("payload"), dict) else {},
                        "time": "",
                    })
            if items:
                return items
        except Exception:
            pass
    try:
        return db.load_ai_trace(thread_id, limit)
    except Exception:
        return []


def storage_status() -> Dict[str, Any]:
    client = _get_redis()
    return {
        "redis": bool(client),
        "redis_url": REDIS_URL[:20] + ("..." if len(REDIS_URL) > 20 else "") if REDIS_URL else "",
        "redis_error": _REDIS_ERROR,
        "state_ttl_seconds": STATE_TTL_SECONDS,
        "trace_ttl_seconds": TRACE_TTL_SECONDS,
    }
