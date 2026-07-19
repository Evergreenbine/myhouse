# -*- coding: utf-8 -*-
"""AI 记忆分层。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import local_db as db


def _clean_dict(data: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    return {key: data.get(key) for key in keys if data.get(key) not in {None, ""}}


def build_memory_layers(
    *,
    session_context: Optional[Dict[str, Any]] = None,
    prompt: str = "",
    intent: Optional[Dict[str, Any]] = None,
    workflow_state: Optional[Dict[str, Any]] = None,
    tool_plan: Optional[Dict[str, Any]] = None,
    pending_actions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    context = session_context if isinstance(session_context, dict) else {}
    profile = db.load_app_user() or {}
    short_term = _clean_dict(context, [
        "thread_id",
        "building_id",
        "building_name",
        "room_id",
        "room_number",
        "tenant_id",
        "tenant_name",
        "month",
        "active_workflow",
    ])
    if prompt:
        short_term["last_prompt"] = prompt[:160]
    if isinstance(intent, dict) and intent.get("workflow"):
        short_term["intent"] = {
            "workflow": intent.get("workflow"),
            "confidence": intent.get("confidence"),
        }

    long_term = _clean_dict(profile, [
        "ai_nickname",
        "user_nickname",
        "selected_building_id",
        "selected_building_name",
        "plan_year",
        "plan_month",
    ])
    if context.get("user_id") not in {None, ""}:
        long_term["user_id"] = context.get("user_id")

    layers = {
        "short_term": short_term,
        "workflow_state": workflow_state if isinstance(workflow_state, dict) else {},
        "long_term": long_term,
        "pending_actions": [
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "label": item.get("label"),
                "status": item.get("status", "pending"),
            }
            for item in (pending_actions or [])
            if isinstance(item, dict)
        ],
        "tool_plan": tool_plan if isinstance(tool_plan, dict) else {},
    }
    return layers


def format_memory_layers(layers: Dict[str, Any]) -> str:
    if not isinstance(layers, dict):
        return ""
    parts = []
    short_term = layers.get("short_term") if isinstance(layers.get("short_term"), dict) else {}
    workflow_state = layers.get("workflow_state") if isinstance(layers.get("workflow_state"), dict) else {}
    long_term = layers.get("long_term") if isinstance(layers.get("long_term"), dict) else {}
    pending_actions = layers.get("pending_actions") if isinstance(layers.get("pending_actions"), list) else []
    tool_plan = layers.get("tool_plan") if isinstance(layers.get("tool_plan"), dict) else {}

    if short_term:
        parts.append("短期上下文：" + ", ".join(f"{k}={v}" for k, v in short_term.items()))
    if workflow_state:
        parts.append("流程状态：" + ", ".join(f"{k}={v}" for k, v in workflow_state.items() if v not in {None, "", [], {}}))
    if long_term:
        parts.append("长期偏好：" + ", ".join(f"{k}={v}" for k, v in long_term.items()))
    if pending_actions:
        parts.append("待确认操作：" + ", ".join(f"{item.get('label') or item.get('type')}" for item in pending_actions[:5]))
    if tool_plan:
        parts.append("工具计划：" + ", ".join(f"{k}={v}" for k, v in tool_plan.items() if v not in {None, "", [], {}}))
    return "\n".join(parts)
