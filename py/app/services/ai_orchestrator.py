# -*- coding: utf-8 -*-
"""AIChat 的 Skill 编排器。

流程：
1. 用 Skill.md 做语义检索，给模型明确业务能力边界。
2. 暴露白名单工具，让模型按需查询实时业务数据。
3. 工具执行后再让模型生成最终回答。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import date
from typing import Any, Dict, List, Optional, TypedDict

import local_db as db
from ai_service import ai_svc

from app.services.ai_context import build_rental_ai_context
from app.services.skill_executor import execute_tool, get_tool_schemas
from app.services.skill_registry import format_skill_hits
from app.services.skill_vector_store import search_skills

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - dependency may be installed only in deployed env
    END = START = None
    StateGraph = None

try:
    from langgraph.checkpoint.memory import MemorySaver
except Exception:  # pragma: no cover - optional local dependency
    MemorySaver = None

try:
    from langgraph.checkpoint.sqlite import SqliteSaver
except Exception:  # pragma: no cover - optional local dependency
    SqliteSaver = None


class AIChatGraphState(TypedDict, total=False):
    data: Dict[str, Any]
    thread_id: str
    prompt: str
    history: List[Dict[str, Any]]
    pending_action_command: str
    intent: Dict[str, Any]
    workflow_state: Dict[str, Any]
    tool_plan: Dict[str, Any]
    messages: List[Dict[str, Any]]
    tools: List[Dict[str, Any]]
    model_response: Dict[str, Any]
    last_tool_results: List[Dict[str, Any]]
    skill_hits: List[Dict[str, Any]]
    tool_round: int
    result: Dict[str, Any]


_CHAT_GRAPH = None
_CHAT_CHECKPOINTER_CONN = None
_SEMANTIC_INTENT_CACHE: Dict[str, Dict[str, Any]] = {}
_SEMANTIC_INTENT_CACHE_LIMIT = 64
_STATUS_LISTENERS: Dict[str, List[Any]] = {}
_STATUS_LISTENERS_LOCK = threading.Lock()


def _status_text(event: str, payload: Optional[Dict[str, Any]] = None) -> str:
    labels = {
        "graph_start": "\u6b63\u5728\u7406\u89e3\u4f60\u7684\u95ee\u9898",
        "route": "\u6b63\u5728\u5224\u65ad\u4e1a\u52a1\u6d41\u7a0b",
        "pending_command": "\u6b63\u5728\u6267\u884c\u786e\u8ba4\u64cd\u4f5c",
        "empty_prompt": "\u6b63\u5728\u5904\u7406\u5f85\u786e\u8ba4\u64cd\u4f5c",
        "contract_form": "\u6b63\u5728\u6574\u7406\u5408\u540c\u4fe1\u606f",
        "meter_reading": "\u6b63\u5728\u5904\u7406\u6c34\u7535\u8868\u8bfb\u6570",
        "prepare_context": "\u6b63\u5728\u51c6\u5907\u4e1a\u52a1\u4e0a\u4e0b\u6587",
        "semantic_intent": "\u6b63\u5728\u8bc6\u522b\u610f\u56fe",
        "call_model": "\u6b63\u5728\u601d\u8003\u4e0b\u4e00\u6b65",
        "run_tools": "\u6b63\u5728\u8c03\u7528\u4e1a\u52a1\u5de5\u5177",
        "finalize": "\u6b63\u5728\u6574\u7406\u56de\u590d",
        "graph_end": "\u5df2\u5b8c\u6210",
    }
    return labels.get(str(event or ""), "\u6b63\u5728\u5904\u7406")


def add_status_listener(thread_id: str, listener: Any) -> None:
    if not thread_id or thread_id == "transient":
        return
    with _STATUS_LISTENERS_LOCK:
        _STATUS_LISTENERS.setdefault(thread_id, []).append(listener)


def remove_status_listener(thread_id: str, listener: Any) -> None:
    if not thread_id:
        return
    with _STATUS_LISTENERS_LOCK:
        listeners = _STATUS_LISTENERS.get(thread_id) or []
        _STATUS_LISTENERS[thread_id] = [item for item in listeners if item is not listener]
        if not _STATUS_LISTENERS[thread_id]:
            _STATUS_LISTENERS.pop(thread_id, None)


def _emit_status(thread_id: str, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
    with _STATUS_LISTENERS_LOCK:
        listeners = list(_STATUS_LISTENERS.get(thread_id) or [])
    if not listeners:
        return
    item = {
        "event": event,
        "text": _status_text(event, payload),
        "payload": payload or {},
    }
    for listener in listeners:
        try:
            listener(item)
        except Exception:
            pass


def _create_chat_checkpointer():
    global _CHAT_CHECKPOINTER_CONN
    if SqliteSaver is not None:
        os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
        _CHAT_CHECKPOINTER_CONN = sqlite3.connect(db.DB_PATH, check_same_thread=False)
        return SqliteSaver(_CHAT_CHECKPOINTER_CONN)
    if MemorySaver is not None:
        return MemorySaver()
    return None


_CHAT_CHECKPOINTER = _create_chat_checkpointer()


WORKFLOW_CONFIGS: Dict[str, Dict[str, Any]] = {
    "contract_create": {
        "label": "新建合同",
        "required_fields": ["room_number", "tenant_name", "start_date", "monthly_rent"],
        "tools": ["contract_create_from_ai", "contract_tenant_list_active_contracts"],
        "max_tool_rounds": 3,
    },
    "contract_manage": {
        "label": "修改合同",
        "required_fields": [],
        "tools": ["contract_tenant_get_contract_detail", "contract_update_from_ai"],
        "max_tool_rounds": 3,
    },
    "meter_reading": {
        "label": "录入水电表",
        "required_fields": ["room_number"],
        "tools": ["meter_reading_get_room_reading", "meter_reading_save_from_ai"],
        "max_tool_rounds": 4,
    },
    "bill_create": {
        "label": "生成账单",
        "required_fields": [],
        "tools": ["bill_generate_draft", "bill_validate_preview", "bill_create_from_ai"],
        "max_tool_rounds": 4,
    },
    "payment": {
        "label": "确认收款",
        "required_fields": [],
        "tools": ["bill_get_bill_detail", "payment_confirm_from_ai"],
        "max_tool_rounds": 3,
    },
    "query": {
        "label": "业务查询",
        "required_fields": [],
        "tools": [],
        "max_tool_rounds": 2,
    },
    "image_ocr": {
        "label": "图片识别",
        "required_fields": [],
        "tools": ["meter_reading_save_from_ai", "bill_get_receipt_image_data"],
        "max_tool_rounds": 4,
    },
}


DOMAIN_RULES = [
    "所有写库动作必须先返回待确认操作，用户确认后才能执行。",
    "有效合同不能重复新建；同一房间已有有效合同时必须提示用户处理原合同。",
    "押一月、押一个月房租等于当前月租金额。",
    "水电单价可以为 0，表示该合同或账单不收对应费用。",
    "合同结束日期可以为空；合同开始日期不能为空。",
    "覆盖账单或修改已收账单时必须提示新旧金额差异。",
    "录入水电读数时要结合楼栋、房间、月份、表类型和历史读数校验。",
]


PENDING_ACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ai_suggest_actions",
            "description": "给用户展示可点击的建议方案按钮。只用于建议、下一步选择或非破坏性流程分支；需要写入数据时仍应使用待确认操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "actions": {
                        "type": "array",
                        "description": "建议方案列表，1 到 4 个；只有一个明确下一步时也要返回。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "按钮文案，尽量短，例如：覆盖旧账单。"},
                                "prompt": {"type": "string", "description": "点击后发送给助手的完整用户意图。"},
                                "description": {"type": "string", "description": "可选的简短说明，说明该方案会做什么。"},
                            },
                            "required": ["label", "prompt"],
                        },
                    }
                },
                "required": ["actions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ai_confirm_pending_action",
            "description": "确认并执行一个待确认操作，例如录入读数、保存账单、修改合同或确认收款。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_id": {"type": "string", "description": "待确认操作 ID；如果只有一个待确认操作，可不传。"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ai_cancel_pending_action",
            "description": "取消一个待确认操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_id": {"type": "string", "description": "待确认操作 ID；如果只有一个待确认操作，可不传。"}
                },
                "required": [],
            },
        },
    },
]


GUIDED_HELP_REPLY = (
    "我还不能确定你遇到的具体问题。请告诉我：你正在做什么（查询、录入读数、生成账单或收款），"
    "涉及哪个楼栋、房间和月份，以及现在卡在哪一步或页面显示了什么。"
    "我会根据这些信息告诉你下一步怎么处理。"
)


def _normalize_uploaded_meter_type(value: Any) -> str:
    """兼容前端英文枚举和模型返回的中文表具类型。"""
    text = str(value or "").strip().lower()
    if text in {"water", "water_meter", "水", "水表"} or "水" in text:
        return "water"
    if text in {"electric", "electricity", "power", "electric_meter", "电", "电表"} or "电" in text:
        return "electric"
    return ""


def _looks_like_technical_failure(reply: str) -> bool:
    text = str(reply or "").lower()
    markers = (
        "连接失败", "api错误", "api 错误", "请求失败", "服务暂时不可用",
        "service unavailable", "timeout", "timed out", "traceback", "exception",
        "工具不在白名单", "参数不是合法 json", "🐱",
    )
    return any(marker in text for marker in markers)


def _has_internal_tool_failure(tool_results: List[Dict[str, Any]]) -> bool:
    return any(isinstance(result, dict) and result.get("ok") is False for result in tool_results)


def _looks_like_contract_create(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text:
        return False
    create_words = (
        "新建", "新增", "创建", "录入", "签订", "签",
        "建个", "建一个", "办个", "办一个", "做个", "做一个",
    )
    contract_words = ("合同", "租约", "租房")
    if any(word in text for word in create_words) and any(word in text for word in contract_words):
        return True
    return "入住" in text and ("房" in text or re.search(r"\d{2,5}", text))


def _recent_text(data: Dict[str, Any], limit: int = 4) -> str:
    parts = [str(data.get("prompt") or "")]
    history = data.get("history") or []
    for item in history[-limit:]:
        if isinstance(item, dict):
            parts.append(str(item.get("content") or ""))
    return "\n".join(part for part in parts if part)


def _session_context(data: Dict[str, Any]) -> Dict[str, Any]:
    context = data.get("session_context")
    return dict(context) if isinstance(context, dict) else {}


def _thread_id(data: Dict[str, Any]) -> str:
    context = _session_context(data)
    for key in ("chat_thread_id", "thread_id", "conversation_id"):
        value = data.get(key)
        if value not in {None, ""}:
            return str(value)
    value = context.get("thread_id")
    if value not in {None, ""}:
        return str(value)
    return "transient"


def _load_thread_state(thread_id: str) -> Dict[str, Any]:
    if not thread_id or thread_id == "transient":
        return {}
    try:
        state = db.load_ai_thread_state(thread_id)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _persist_thread_state(thread_id: str, result: Dict[str, Any]) -> None:
    if not thread_id or thread_id == "transient" or not isinstance(result, dict):
        return
    try:
        state = {
            "thread_id": thread_id,
            "session_context": result.get("session_context") or result.get("response", {}).get("session_context") or {},
            "last_intent": result.get("intent") or {},
            "workflow_state": result.get("workflow_state") or {},
            "tool_plan": result.get("tool_plan") or {},
        }
        db.save_ai_thread_state(thread_id, state)
    except Exception:
        pass


def _hydrate_thread_data(data: Dict[str, Any]) -> Dict[str, Any]:
    next_data = dict(data or {})
    thread_id = _thread_id(next_data)
    stored = _load_thread_state(thread_id)
    stored_context = stored.get("session_context") if isinstance(stored, dict) else {}
    incoming_context = _session_context(next_data)
    merged_context = {}
    if isinstance(stored_context, dict):
        merged_context.update(stored_context)
    merged_context.update(incoming_context)
    merged_context["thread_id"] = thread_id
    if isinstance(stored.get("last_intent"), dict) and "last_intent" not in merged_context:
        merged_context["last_intent"] = stored.get("last_intent")
    if isinstance(stored.get("workflow_state"), dict) and "workflow_state" not in merged_context:
        merged_context["workflow_state"] = stored.get("workflow_state")
    next_data["session_context"] = merged_context
    next_data["chat_thread_id"] = thread_id
    return next_data


def _trace_thread(thread_id: str, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
    if not thread_id or thread_id == "transient":
        return
    compact_payload = _compact_trace_payload(payload or {})
    _emit_status(thread_id, event, compact_payload)
    try:
        db.append_ai_trace(thread_id, event, compact_payload)
    except Exception:
        pass


def _trace_state(state: AIChatGraphState, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
    thread_id = str(state.get("thread_id") or _thread_id(state.get("data") or {}))
    _trace_thread(thread_id, event, payload)


def _compact_trace_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    def compact(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): compact(v) for k, v in list(value.items())[:24]}
        if isinstance(value, list):
            return [compact(item) for item in value[:12]]
        if isinstance(value, str) and len(value) > 500:
            return value[:500] + "...[truncated]"
        return value
    return compact(payload)


def _strip_meter_month_text(text: str) -> str:
    return re.sub(r"(?:20\d{2}\s*(?:[-/年])\s*)?(?:0?[1-9]|1[0-2])\s*月份?", " ", str(text or ""))


def _extract_meter_reading_values(prompt: str) -> Dict[str, str]:
    text = str(prompt or "")
    values: Dict[str, str] = {}
    number_pattern = r"\d+(?:\.\d+)?"
    combo = re.search(r"(?:水\s*电|水电)", text)
    if combo:
        tail = _strip_meter_month_text(text[combo.end():])
        numbers = re.findall(number_pattern, tail)
        if len(numbers) >= 2:
            values["water"] = numbers[0]
            values["electric"] = numbers[1]
        return values
    water = re.search(r"水(?!\s*电)(?:表)?(?:读数)?\s*(?:是|为|=|:|：)?\s*(" + number_pattern + r")", text)
    electric = re.search(r"电(?!\s*费)(?:表)?(?:读数)?\s*(?:是|为|=|:|：)?\s*(" + number_pattern + r")", text)
    if water:
        values["water"] = water.group(1)
    if electric:
        values["electric"] = electric.group(1)
    return values


def _looks_like_meter_reading_statement(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text or not re.search(r"\d", text):
        return False
    has_meter_words = any(word in text for word in ("水电", "水表", "电表", "水电表", "读数", "抄表")) or ("水" in text and "电" in text)
    if not has_meter_words:
        return False
    has_contract_price_words = any(word in text for word in ("房租", "月租", "租金", "押", "保证金", "合同"))
    has_explicit_meter_words = any(word in text for word in ("水表", "电表", "水电表", "读数", "抄表"))
    if has_contract_price_words and not has_explicit_meter_words:
        return False
    return bool(_extract_meter_reading_values(text))


def _prompt_workflow(prompt: str) -> str:
    text = str(prompt or "").strip()
    if not text:
        return ""
    if _looks_like_meter_reading_statement(text):
        return "meter_reading"
    if any(word in text for word in ("水电表", "水表", "电表", "抄表", "表读数", "录读数", "录入读数")):
        return "meter_reading"
    if re.search(r"(?:继续|接着).{0,8}(?:合同|租约)", text):
        return "contract_create"
    if _looks_like_contract_create(text):
        return "contract_create"
    if "合同" in text and any(word in text for word in ("修改", "变更", "更新", "调整", "退租", "恢复")):
        return "contract_manage"
    if any(word in text for word in ("生成账单", "新建账单", "录账单", "账单草稿")):
        return "bill_create"
    if any(word in text for word in ("确认收款", "登记收款", "已经交租", "已交租")):
        return "payment"
    if any(word in text for word in ("查询", "查一下", "看看", "多少", "哪些", "有没有", "待收", "收租进度", "合同详情", "空置", "到期")):
        return "query"
    return ""


def _month_hint(prompt: str) -> str:
    text = str(prompt or "")
    match = re.search(r"(20\d{2})\s*(?:[-/年])\s*(0?[1-9]|1[0-2])\s*月?", text)
    if match:
        return "{}-{:02d}".format(match.group(1), int(match.group(2)))
    match = re.search(r"(?<!\d)(0?[1-9]|1[0-2])\s*月份?", text)
    if match:
        return "{}-{:02d}".format(date.today().year, int(match.group(1)))
    match = re.search(r"(20\d{2})[-/年](0?[1-9]|1[0-2])", text)
    if match:
        return "{}-{:02d}".format(match.group(1), int(match.group(2)))
    match = re.search(r"(?<!\d)(0?[1-9]|1[0-2])\s*月", text)
    if match:
        return "{}-{:02d}".format(date.today().year, int(match.group(1)))
    if "本月" in text or "这个月" in text:
        return date.today().strftime("%Y-%m")
    if "上月" in text or "上个月" in text:
        year = date.today().year
        month = date.today().month - 1
        if month == 0:
            year -= 1
            month = 12
        return "{}-{:02d}".format(year, month)
    return ""


def _extract_common_fields(prompt: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    building = _known_building_hint(prompt)
    if building:
        fields.update(building)
    room_number = _room_number_hint(prompt)
    if room_number:
        fields["room_number"] = room_number
    month = _month_hint(prompt)
    if month:
        fields["month"] = month
    return fields


def _context_location_fields(context: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    sources: List[Dict[str, Any]] = []
    if isinstance(context, dict):
        sources.append(context)
        draft = context.get("contract_draft")
        if isinstance(draft, dict):
            sources.append(draft)
        workflow_state = context.get("workflow_state")
        workflow_fields = workflow_state.get("fields") if isinstance(workflow_state, dict) else None
        if isinstance(workflow_fields, dict):
            sources.append(workflow_fields)
        suspended = context.get("suspended_contract")
        if isinstance(suspended, dict):
            sources.append(suspended)
            suspended_draft = suspended.get("contract_draft")
            if isinstance(suspended_draft, dict):
                sources.append(suspended_draft)
    for source in reversed(sources):
        for key in ("building_id", "building_name", "room_id", "room_number", "tenant_id", "tenant_name"):
            value = source.get(key)
            if value not in {None, ""}:
                fields[key] = value
    return fields


def _semantic_intent_history(data: Dict[str, Any]) -> List[Dict[str, str]]:
    history = data.get("history") or []
    brief: List[Dict[str, str]] = []
    for item in history[-6:]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        brief.append({
            "role": str(item.get("role") or item.get("type") or ""),
            "content": content[:400],
        })
    return brief


def _context_subset(context: Dict[str, Any], keys: tuple[str, ...]) -> Dict[str, Any]:
    subset: Dict[str, Any] = {}
    for key in keys:
        value = context.get(key)
        if value is not None and value != "":
            subset[key] = value
    return subset


def _semantic_intent_cache_key(data: Dict[str, Any]) -> str:
    context = _session_context(data)
    context_subset = _context_subset(context, (
        "active_workflow", "last_completed_workflow", "building_id", "building_name",
        "room_id", "room_number", "tenant_id", "tenant_name", "workflow_state",
        "contract_draft", "suspended_contract", "last_intent",
    ))
    payload = {
        "prompt": str(data.get("prompt") or "").strip(),
        "history": _semantic_intent_history(data),
        "context": context_subset,
        "has_images": bool(data.get("uploaded_images") or data.get("uploaded_image") or data.get("ocr_number") is not None),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _semantic_workflow_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "contract": "contract_create",
        "create_contract": "contract_create",
        "new_contract": "contract_create",
        "contract_update": "contract_manage",
        "contract_query": "query",
        "contract_detail": "query",
        "meter": "meter_reading",
        "meter_save": "meter_reading",
        "reading": "meter_reading",
        "bill": "bill_create",
        "create_bill": "bill_create",
        "receipt": "bill_create",
        "payment_confirm": "payment",
        "rent_payment": "payment",
        "unknown": "query",
    }
    workflow = aliases.get(raw, raw)
    allowed = set(WORKFLOW_CONFIGS.keys()) | {"empty", "pending_action"}
    return workflow if workflow in allowed else ""


def _semantic_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _normalize_semantic_intent(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    workflow = _semantic_workflow_name(raw.get("workflow") or raw.get("intent") or raw.get("name"))
    if not workflow:
        return {}
    fields = raw.get("fields")
    return {
        "name": workflow,
        "workflow": workflow,
        "confidence": _semantic_confidence(raw.get("confidence", 0.0)),
        "source": "ai_semantic",
        "fields": fields if isinstance(fields, dict) else {},
        "reason": str(raw.get("reason") or "")[:200],
    }


def _should_reclassify_with_ai(data: Dict[str, Any], rules_workflow: str) -> bool:
    prompt = str(data.get("prompt") or "").strip()
    if not prompt or data.get("_skip_semantic_intent"):
        return False
    context = _session_context(data)
    active = str(context.get("active_workflow") or "")
    if rules_workflow in {"meter_reading", "contract_create", "contract_manage", "bill_create", "payment", "image_ocr"}:
        return False
    if rules_workflow == "query" and active:
        return True
    if rules_workflow:
        return False
    if active == "contract_create" and _extract_contract_create_hint(prompt):
        return False
    return bool(active)


def _semantic_intent_from_ai(data: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return {}
    cache_key = _semantic_intent_cache_key(data)
    if cache_key in _SEMANTIC_INTENT_CACHE:
        return dict(_SEMANTIC_INTENT_CACHE[cache_key])

    call_json = getattr(ai_svc, "call_json", None)
    if not callable(call_json):
        return {}
    context = _session_context(data)
    user_payload = {
        "current_prompt": prompt,
        "recent_history": _semantic_intent_history(data),
        "session_context": _context_subset(context, (
            "active_workflow", "workflow_state", "contract_draft",
            "building_name", "room_number", "tenant_name", "last_intent",
        )),
        "has_uploaded_images": bool(data.get("uploaded_images") or data.get("uploaded_image")),
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是租房管理系统的语义意图识别器，只返回 JSON 对象，不要 Markdown。"
                "workflow 只能是 contract_create、contract_manage、meter_reading、bill_create、payment、query、image_ocr、empty。"
                "active_workflow 只是上下文线索，不能强行覆盖当前用户的新意图。"
                "如果用户问“有合同了吗/住哪/查一下/多少/哪些”，优先判为 query；"
                "如果用户说“水电读数/抄表/6月份水电是346 9150”，判为 meter_reading；"
                "如果用户明确新建/新增/签订合同，判为 contract_create；"
                "如果用户是在修改已有合同，判为 contract_manage。"
                "返回字段：workflow、confidence(0-1)、fields、reason。"
            ),
        },
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
    ]
    raw, err = call_json(messages, max_tokens=260, temperature=0.0, timeout=20)
    if err or not isinstance(raw, dict):
        _trace_thread(_thread_id(data), "semantic_intent_error", {"error": err})
        return {}
    intent = _normalize_semantic_intent(raw)
    if not intent:
        return {}
    if len(_SEMANTIC_INTENT_CACHE) >= _SEMANTIC_INTENT_CACHE_LIMIT:
        _SEMANTIC_INTENT_CACHE.clear()
    _SEMANTIC_INTENT_CACHE[cache_key] = dict(intent)
    _trace_thread(_thread_id(data), "semantic_intent", intent)
    return intent


def _detect_intent(data: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    context = _session_context(data)
    pending_command = str(data.get("pending_action_command") or "").strip().lower()
    if pending_command in {"confirm", "cancel"}:
        return {
            "name": "pending_action_" + pending_command,
            "workflow": str(context.get("active_workflow") or "pending_action"),
            "confidence": 1.0,
            "source": "pending_command",
            "fields": {},
        }
    rules_workflow = _prompt_workflow(prompt)
    semantic = _semantic_intent_from_ai(data) if _should_reclassify_with_ai(data, rules_workflow) else {}
    workflow = str(semantic.get("workflow") or "")
    source = str(semantic.get("source") or "rules")
    confidence = _semantic_confidence(semantic.get("confidence", 0.0)) if semantic else 0.0
    if not workflow or confidence < 0.45:
        if rules_workflow:
            workflow = rules_workflow
            source = "rules"
            confidence = max(confidence, 0.9)
    if not workflow and data.get("uploaded_images"):
        workflow = "image_ocr"
        source = "rules"
        confidence = max(confidence, 0.85)
    if not workflow and context.get("active_workflow") and prompt:
        workflow = str(context.get("active_workflow") or "")
        source = "context"
        confidence = max(confidence, 0.55)
    if not workflow:
        workflow = "query" if prompt else "empty"
        source = "rules"
        confidence = max(confidence, 0.65)
    fields = {}
    if isinstance(semantic.get("fields"), dict):
        fields.update({k: v for k, v in semantic.get("fields", {}).items() if v not in {None, ""}})
    fields.update(_extract_common_fields(prompt))
    if workflow == "meter_reading":
        inherited = _context_location_fields(context)
        fields = {**inherited, **fields}
    if workflow == "contract_create":
        fields.update(_extract_contract_create_hint(prompt))
    return {
        "name": workflow,
        "workflow": workflow,
        "confidence": confidence or (0.9 if workflow not in {"query", "empty"} else 0.65),
        "source": source,
        "fields": fields,
    }


def _tool_plan_for_intent(intent: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    workflow = str(intent.get("workflow") or intent.get("name") or "")
    config = WORKFLOW_CONFIGS.get(workflow, WORKFLOW_CONFIGS["query"])
    steps = []
    if workflow == "contract_create":
        steps = ["抽取合同字段", "查楼栋/房间/租客", "缺字段则返回表单", "信息完整后生成确认卡片"]
    elif workflow == "meter_reading":
        steps = ["定位楼栋房间和月份", "读取或识别水电表读数", "校验历史读数", "生成待确认读数"]
    elif workflow == "bill_create":
        steps = ["查有效合同", "查水电读数和旧账单", "生成账单草稿", "提示覆盖差异并等待确认"]
    elif workflow == "payment":
        steps = ["定位账单", "校验应收已收", "生成收款确认卡片"]
    elif workflow == "contract_manage":
        steps = ["定位有效合同", "解析要修改的字段", "校验业务规则", "生成修改确认卡片"]
    else:
        steps = ["查询实时业务数据", "整理结果", "给出下一步建议"]
    return {
        "workflow": workflow,
        "allowed_tools": config.get("tools", []),
        "max_tool_rounds": config.get("max_tool_rounds", 2),
        "steps": steps,
    }


def _domain_rule_summary() -> str:
    return "\n".join("- " + rule for rule in DOMAIN_RULES)


def _workflow_required_fields(workflow: str) -> List[str]:
    config = WORKFLOW_CONFIGS.get(workflow) or {}
    return list(config.get("required_fields") or [])


def _workflow_state_from_data(
    data: Dict[str, Any],
    intent: Optional[Dict[str, Any]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    context = _session_context(data)
    previous = context.get("workflow_state")
    state = dict(previous) if isinstance(previous, dict) else {}
    intent = intent or _detect_intent(data)
    workflow = str(intent.get("workflow") or intent.get("name") or "")
    if workflow and workflow != "empty":
        if state.get("name") != workflow:
            state = {"name": workflow, "status": "active", "fields": {}, "missing": []}
        state["name"] = workflow
        state["label"] = WORKFLOW_CONFIGS.get(workflow, {}).get("label", workflow)
    fields = dict(state.get("fields") or {})
    if isinstance(intent.get("fields"), dict):
        fields.update({k: v for k, v in intent.get("fields", {}).items() if v not in {None, ""}})
    if workflow == "contract_create":
        contract_args = _contract_create_args({**data, "session_context": context})
        fields.update({k: v for k, v in contract_args.items() if v not in {None, ""}})
    for tool_name, payload in _tool_result_payloads(tool_results or []):
        if tool_name == "contract_create_from_ai":
            form = payload.get("form_action")
            if isinstance(form, dict):
                values = form.get("values")
                if isinstance(values, dict):
                    fields.update({k: v for k, v in values.items() if v not in {None, ""}})
                state["missing"] = list(form.get("missing") or [])
                state["status"] = "waiting_for_fields" if state["missing"] else "active"
        pending = payload.get("pending_action")
        if isinstance(pending, dict):
            state["status"] = "awaiting_confirmation"
    for tool_name, payload in _tool_result_payloads(tool_results or []):
        if tool_name == "confirm_create_contract" and payload.get("success"):
            state["status"] = "completed"
    required = _workflow_required_fields(workflow)
    missing = [field for field in required if not str(fields.get(field) or "").strip()]
    if missing:
        state["missing"] = missing
        if state.get("status") not in {"awaiting_confirmation", "completed"}:
            state["status"] = "waiting_for_fields"
    elif required and state.get("status") == "waiting_for_fields":
        state["status"] = "active"
    state["fields"] = fields
    return {key: value for key, value in state.items() if value is not None and value != ""}


def _known_building_hint(prompt: str) -> Dict[str, Any]:
    text = re.sub(r"[，。！？,.!?\s]", "", str(prompt or ""))
    matches = []
    for building in db.get_buildings() or []:
        name = str(building.get("name") or "").strip()
        if name and name in text:
            matches.append(building)
    if len(matches) != 1:
        return {}
    return {
        "building_id": matches[0].get("id"),
        "building_name": str(matches[0].get("name") or ""),
    }


def _room_number_hint(prompt: str) -> str:
    text = str(prompt or "")
    patterns = (
        r"(?:房间号|房号)\s*[:：]?\s*(\d{2,5})(?!\d)",
        r"(?<!\d)(\d{2,5})\s*(?:房|室|号房)(?!\d)",
        r"(?<!\d)(\d{2,5})\s*(?:的|房)?\s*(?:房租|月租|租金|水费|电费|押金|保证金|水|电)(?:\s*(?:是|为|=|:|：))?",
        r"(?<!\d)(\d{2,5})(?:的)?(?:水电表|水表|电表)",
        r"(?:帮我|给我|接着录|继续录|再录)\D{0,8}(\d{2,5})(?!\d)",
        r"(?<!\d)(\d{2,5})\D{0,8}(?:新建|新增|创建|录入|签订|建(?:个|一个)?|办(?:个|一个)?|做(?:个|一个)?).{0,6}(?:合同|租约)",
        r"(?:新建|新增|创建|录入|签订|建(?:个|一个)?|办(?:个|一个)?|做(?:个|一个)?)\D{0,8}(\d{2,5})\D{0,6}(?:合同|租约)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _float_hint(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _deposit_month_count(text: str) -> Optional[float]:
    match = re.search(r"押(?:金)?\s*(\d+(?:\.\d+)?)\s*(?:个)?月(?:房租|租金|月租)?", text)
    if match:
        return _float_hint(match.group(1))
    chinese_months = {
        "一": 1.0,
        "一个": 1.0,
        "二": 2.0,
        "两": 2.0,
        "两个": 2.0,
        "三": 3.0,
        "三个": 3.0,
    }
    match = re.search(r"押(?:金)?\s*(一个|两个|三个|一|二|两|三)\s*月?(?:房租|租金|月租)?", text)
    if match:
        return chinese_months.get(match.group(1))
    if "押一付" in text:
        return 1.0
    return None


def _contract_create_args(data: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    context = _session_context(data)
    draft = context.get("contract_draft")
    workflow_state = context.get("workflow_state")
    if not isinstance(draft, dict) and isinstance(workflow_state, dict) and workflow_state.get("name") == "contract_create":
        fields = workflow_state.get("fields")
        if isinstance(fields, dict):
            draft = fields
    suspended = context.get("suspended_contract")
    if not isinstance(draft, dict) and isinstance(suspended, dict):
        draft = suspended.get("contract_draft")
        for key in ("building_id", "building_name", "room_id", "room_number"):
            if context.get(key) in {None, ""} and suspended.get(key) not in {None, ""}:
                context[key] = suspended.get(key)
    args = dict(draft) if isinstance(draft, dict) else {}
    room_number = _room_number_hint(prompt)
    previous_room = str(args.get("room_number") or "").strip()
    if room_number and previous_room and room_number != previous_room:
        args = {
            key: value for key, value in args.items()
            if key in {"building_id", "building_name"}
        }
    for key in (
        "building_id", "building_name", "room_id", "room_number", "tenant_id", "tenant_name",
        "start_date", "end_date", "monthly_rent", "water_unit_price", "electric_unit_price",
        "deposit", "water_meter_id", "electric_meter_id",
    ):
        if args.get(key) in {None, ""} and context.get(key) not in {None, ""}:
            args[key] = context.get(key)

    extracted_args = _extract_contract_create_hint(prompt)
    args.update(extracted_args)
    building_hint = _known_building_hint(prompt)
    if building_hint:
        args.update(building_hint)
    if room_number:
        args["room_number"] = room_number
        if "room_id" not in extracted_args:
            args.pop("room_id", None)
    return args


def _should_fallback_contract_create(data: Dict[str, Any]) -> bool:
    prompt = str(data.get("prompt") or "").strip()
    workflow = _prompt_workflow(prompt)
    if workflow and workflow != "contract_create":
        return False
    if _looks_like_contract_create(prompt):
        return True
    context = _session_context(data)
    if context.get("active_workflow") == "contract_create":
        return bool(prompt and _extract_contract_create_hint(prompt))
    recent = _recent_text(data)
    has_contract_create_context = _looks_like_contract_create(recent) or (
        "新建合同" in recent and ("补充" in recent or "必填" in recent or "空置" in recent)
    )
    has_location_hint = bool(_room_number_hint(prompt))
    return has_contract_create_context and has_location_hint


def _extract_contract_create_hint(prompt: str) -> Dict[str, Any]:
    text = str(prompt or "").strip()
    args: Dict[str, Any] = {}
    form_patterns = {
        "building_id": r"楼栋ID\s*([^，,。]+)",
        "building_name": r"楼栋名称\s*([^，,。]+)",
        "room_id": r"房间ID\s*([^，,。]+)",
        "room_number": r"房间号\s*([^，,。]+)",
        "tenant_id": r"租户ID\s*([^，,。]+)",
        "tenant_name": r"租户姓名\s*([^，,。]+)",
        "start_date": r"合同开始日期\s*([^，,。]+)",
        "end_date": r"合同结束日期\s*([^，,。]+)",
        "monthly_rent": r"月租\s*([^，,。]+)",
        "water_unit_price": r"水费单价\s*([^，,。]+)",
        "electric_unit_price": r"电费单价\s*([^，,。]+)",
        "deposit": r"保证金\s*([^，,。]+)",
        "other_fee_details": r"其它费用\s*([^。]+)",
    }
    for key, pattern in form_patterns.items():
        match = re.search(pattern, text)
        if not match:
            continue
        value = match.group(1).strip()
        if value:
            args[key] = value
    room_number = _room_number_hint(text)
    if room_number and not args.get("room_number"):
        args["room_number"] = room_number
    date_match = re.search(r"(20\d{2}[-/年](?:0?[1-9]|1[0-2])[-/月](?:0?[1-9]|[12]\d|3[01])日?)", text)
    if date_match and not args.get("start_date"):
        args["start_date"] = date_match.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    rent_match = re.search(r"(?:月租|租金|房租)\s*(?:是|为|=|:|：)?\s*(\d+(?:\.\d+)?)", text)
    if rent_match and not args.get("monthly_rent"):
        args["monthly_rent"] = rent_match.group(1)
    deposit_match = re.search(r"(?:押金|保证金)\s*(\d+(?:\.\d+)?)", text)
    if deposit_match and not args.get("deposit"):
        args["deposit"] = deposit_match.group(1)
    deposit_months = _deposit_month_count(text)
    monthly_rent_value = _float_hint(args.get("monthly_rent"))
    if deposit_months is not None and monthly_rent_value is not None and not args.get("deposit"):
        args["deposit"] = str(round(monthly_rent_value * deposit_months, 2)).rstrip("0").rstrip(".")
    water_match = re.search(r"(?:水费(?:单价)?|水)\s*(?:是|为|=|:|：)?\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if water_match and not args.get("water_unit_price"):
        args["water_unit_price"] = water_match.group(1)
    electric_match = re.search(r"(?:电费(?:单价)?|电)\s*(?:是|为|=|:|：)?\s*(\d+(?:\.\d+)?)\s*(?:元|块)?", text)
    if electric_match and not args.get("electric_unit_price"):
        args["electric_unit_price"] = electric_match.group(1)
    other_fee_matches = re.findall(
        r"((?:网|网络|宽带|卫生|管理|物业|停车|清洁|垃圾|公摊|电梯|维修|其它|其他)[\u4e00-\u9fffA-Za-z_-]{0,8}费?)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:元|块)?",
        text,
    )
    ignored_fee_names = {"水", "水费", "电", "电费", "月租", "房租", "租金", "押金", "保证金"}
    other_fees = [
        {"name": name if name.endswith("费") else name + "费", "amount": float(amount)}
        for name, amount in other_fee_matches
        if name not in ignored_fee_names
    ]
    if other_fees and not args.get("other_fee_details"):
        args["other_fee_details"] = other_fees
    return args


def _contract_create_form_fallback(data: Dict[str, Any]) -> Dict[str, Any] | None:
    prompt = str(data.get("prompt") or "").strip()
    if not _should_fallback_contract_create(data):
        return None
    tool_result = execute_tool("contract_create_from_ai", _contract_create_args(data))
    if not isinstance(tool_result, dict):
        return None
    result_data = tool_result.get("data")
    if not isinstance(result_data, dict):
        return None
    form_actions = _collect_form_actions([tool_result])
    pending_actions = _merge_pending_actions(data.get("pending_actions") or [], [tool_result])
    skill_hits = search_skills(prompt, top_k=5)
    if form_actions or pending_actions:
        return _finalize_chat_response("", data, [tool_result], skill_hits)
    message = str(result_data.get("message") or tool_result.get("error") or "新建合同没有完成，请检查表单信息后再提交。").strip()
    session_context = _next_session_context(data, [tool_result])
    return {
        "reply": message,
        "bill_images": [],
        "pending_actions": [],
        "suggested_actions": [],
        "form_actions": [],
        "session_context": session_context,
        "response": {"type": "assistant_message", "content": message, "pending_actions": [], "bill_images": [], "suggested_actions": [], "form_actions": [], "session_context": session_context},
        "skill_hits": [{
            "skill": hit.get("skill"),
            "title": hit.get("title"),
            "backend": hit.get("backend"),
            "score": hit.get("score"),
        } for hit in skill_hits],
    }


def _meter_reading_fallback_args(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    prompt = str(data.get("prompt") or "")
    if not _looks_like_meter_reading_statement(prompt):
        return []
    context = _session_context(data)
    location = _context_location_fields(context)
    prompt_fields = _extract_common_fields(prompt)
    location.update({k: v for k, v in prompt_fields.items() if k in {"building_id", "building_name", "room_number"} and v not in {None, ""}})
    room_number = str(location.get("room_number") or "").strip()
    if not room_number:
        return []
    month = prompt_fields.get("month") or _month_hint(prompt)
    if not month:
        return []
    readings = _extract_meter_reading_values(prompt)
    tool_args = []
    for meter_type in ("water", "electric"):
        reading = readings.get(meter_type)
        if reading in {None, ""}:
            continue
        args = {
            "room_number": room_number,
            "meter_type": meter_type,
            "month": month,
            "reading": reading,
        }
        if location.get("building_id") not in {None, ""}:
            args["building_id"] = location.get("building_id")
        tool_args.append(args)
    return tool_args


def _meter_reading_fallback(data: Dict[str, Any]) -> Dict[str, Any] | None:
    tool_args = _meter_reading_fallback_args(data)
    if not tool_args:
        return None
    tool_results = [execute_tool("meter_reading_save_from_ai", args) for args in tool_args]
    skill_hits = search_skills(str(data.get("prompt") or ""), top_k=5)
    return _finalize_chat_response("已识别到水电表读数，请核对下方待确认操作。", data, tool_results, skill_hits)


def _history_messages(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    messages = []
    for item in history[-10:]:
        role = "assistant" if item.get("role") == "assistant" else "user"
        content = str(item.get("content") or "")
        if content:
            messages.append({"role": role, "content": content})
    return messages


def _sanitize_tool_message(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if key in {"photo", "water_photo", "electric_photo", "uploaded_image"} and item:
                sanitized[key] = "[图片数据已省略]"
            else:
                sanitized[key] = _sanitize_tool_message(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_tool_message(item) for item in value]
    return value


def _json_for_tool(data: Dict[str, Any], limit: int = 12000) -> str:
    text = json.dumps(_sanitize_tool_message(data), ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...工具结果过长，已截断。"


def _extract_tool_call(call: Dict[str, Any]) -> Dict[str, Any]:
    fn = call.get("function") or {}
    return {
        "id": call.get("id") or "",
        "name": fn.get("name") or "",
        "arguments": fn.get("arguments") or "{}",
    }


def _assistant_identity() -> tuple[str, str]:
    config = db.load_app_user() or {}

    def _clean(value: Any, fallback: str) -> str:
        text = re.sub(r"[\r\n\t]+", " ", str(value or "")).strip()
        return (text or fallback)[:20]

    return _clean(config.get("ai_nickname"), "哈基米"), _clean(config.get("user_nickname"), "大王")


def _build_system_prompt(
    prompt: str,
    skill_context: str,
    data_context: str,
    image_context: str = "",
    session_context: Optional[Dict[str, Any]] = None,
    intent: Optional[Dict[str, Any]] = None,
    tool_plan: Optional[Dict[str, Any]] = None,
) -> str:
    ai_nickname, user_nickname = _assistant_identity()
    return (
        f"你的名字是“{ai_nickname}”，你对用户的称呼是“{user_nickname}”。"
        f"当需要自称或称呼用户时，始终使用“{ai_nickname}”和“{user_nickname}”。"
        "你需要用中文回答，简洁、准确、可执行。"
        "优先使用工具查询实时业务数据；工具结果比推测更可靠。"
        "不要编造房间、租客、账单、读数、收款记录。"
        "不要向用户展示程序错误、接口错误、工具名称、异常堆栈或内部日志。"
        "当无法判断该调用哪个工具、工具没有完成或信息不足时，要追问用户正在做什么、涉及的楼栋房间月份、卡在哪一步，并告诉用户补充后可以继续处理。"
        "如果数据没有录入或上下文没有提供，要明确说明缺少什么。"
        "涉及金额时使用人民币并保留两位小数。"
        "读数只返回数字，不附带单位。"
        "识别或处理机械式电表读数时，黑色数字窗口从左到右是整数位，可能是4位、5位或更多，不能截断；标0.1/0.01、红色数字、红框小窗或白底小窗通常是小数位。"
        "租房抄表默认忽略小数位，只录整数；例如黑色整数位2088、右侧0.1小数位9，应按2088处理，不要按20889处理。"
        "识别或处理机械式水表时，优先读取长方形数字窗整数位，忽略下方小圆盘小数位，并去掉前导零；例如00712按712处理。"
        "展示格式要适合聊天窗口：首行先给结论，后面用简短分组和紧凑表格。"
        "不要频繁使用 Markdown 大标题、横线和表情符号；除非确实需要，不要输出 ##、---。"
        "当用户要求输出、生成、查看、复制账单图片或收据图片时，优先调用 bill_get_receipt_image_data。"
        "如果工具返回了账单图片数据，文字回复只需要简短说明已生成图片，不要再重复大段账单明细。"
        "当用户上传水表或电表图片，并要求录入读数时，调用 meter_reading_save_from_ai。"
        "即使该月份已经存在相同读数，只要用户上传了新照片并要求录入，也要调用 meter_reading_save_from_ai 生成更新确认事项，以便保存照片，不能只回复无需重复录入。"
        "上传图片上下文中的类型、读数、表号、楼栋、房间和租客是结构化识别结果；优先使用这些值，不要重新猜测。"
        "涉及图片识别、录入读数或保存账单时，先返回待确认操作，不能因为用户上传图片就直接写入数据库。"
        "当用户继续要求生成账单时，在读数保存成功后调用 bill_create_from_ai。"
        "生成账单时，合同中约定的其它费用会默认带入账单草稿；用户本轮明确添加、删除、清空或修改其它费用时，以用户本轮要求为准。"
        "用户要求添加网费、卫生费等其他费用时，调用 bill_create_from_ai 并通过 other_fee_details 按项目名称和金额逐项传递，不能只传其他费用汇总。"
        "用户要求删除、去掉或取消网费、卫生费等某项其他费用时，调用 bill_create_from_ai，设置 overwrite=true，并通过 remove_other_fee_names 传入要删除的项目名称；用户要求清空全部其他费用时设置 clear_other_fees=true。"
        "删除或修改某个租户账单的其他费用时，如果用户只说租户姓名，没有说房间号，可以把姓名作为 tenant_name 传给 bill_create_from_ai。"
        "删除或清空其他费用也必须先返回待确认操作卡片，确认后再覆盖账单和账单图片。"
        "用户明确要求修改、替换或覆盖已有账单及账单图片时，调用 bill_create_from_ai 并设置 overwrite=true；仍需先返回覆盖确认事项，确认后再更新账单和图片。"
        "如果缺少房间号、月份或水表/电表类型，不要猜测，先请用户补充。"
        "当用户查询合同详情、某租户住哪、某房间当前合同、有效合同列表或合同绑定表具时，优先调用 contract_tenant_get_contract_detail、contract_tenant_list_active_contracts、contract_tenant_get_room_tenant 或 contract_tenant_get_contract_meter_binding。"
        "当用户要求新建、新增、签订或录入租房合同时，调用 contract_create_from_ai；即使缺少租户、房间、合同开始日期或月租，也要调用该工具返回表单卡片，不要只用文字追问。"
        "新建合同表单要尽量带出用户已提供的信息，例如楼栋名称传 building_name、房间号传 room_number、租客姓名传 tenant_name、已说出的月租/押金/水电单价/其它费用也要传入。"
        "业务会话上下文中的楼栋、房间只用于承接省略表达；用户本轮明确说出的业务意图和楼栋房间永远优先。"
        "用户说先做、改做或录入水电表时，应切换到抄表流程，不能因为此前正在新建合同而继续生成合同表单。"
        "当用户要求修改现有合同的月租、水电单价、保证金、合同日期、水电表绑定或合同约定其它费用时，调用 contract_update_from_ai；其它费用通过 other_fee_details 按项目名称和金额逐项传递。"
        "合同结束日期可以改成空值；合同开始日期不能为空，修改开始日期时必须提供具体的 YYYY-MM-DD 日期。"
        "用户只说租户姓名时，可以把姓名作为 tenant_name 传给合同查询和合同修改工具；如果匹配到多个合同，要让用户补充楼栋或房间。"
        "合同新建和合同修改都必须先返回待确认操作；如果同一房间号存在于多个楼栋，要先请用户明确楼栋。"
        "退租、恢复合同、变更租客或更换房间不是普通合同字段修改，也不是新建合同，不能调用 contract_update_from_ai，需明确告诉用户应使用对应业务流程。"
        "当用户要求确认收款、登记收款或标记某房间已经交租时，调用 payment_confirm_from_ai。"
        "确认收款必须先返回待确认操作；未指定金额时默认使用该账单当前全部待收金额，未指定日期时默认今天。"
        "账单仍在录入中或待发送、账单已收完、金额超过待收，或房间和楼栋不明确时，不能直接收款，要向用户说明需要先处理或补充什么。"
        "如果存在待确认操作，且用户通过文字表示确认、可以、录入、保存、执行，就调用 ai_confirm_pending_action；界面按钮会通过同一待确认协议直接执行。"
        "如果用户要求取消待确认操作，就调用 ai_cancel_pending_action。"
        "当你要给用户建议、处理方案、下一步选择或询问用户是否继续业务流程时，即使只有一个选项，也必须调用 ai_suggest_actions 返回可点击按钮，不能只在文字末尾询问；按钮 label 要短，prompt 要写成点击后可直接执行的完整意图。"
        "如果某个选择会直接写入、覆盖、确认收款或修改合同，要优先生成待确认操作卡片，不能只给建议按钮。"
        "除 meter_reading_save_from_ai、bill_create_from_ai、contract_create_from_ai、contract_update_from_ai 和 payment_confirm_from_ai 这些待确认工具外，不能声称已经写入、发送账单、确认收款、新建或修改合同、覆盖读数。"
        "保存读数或生成账单后，要根据工具结果明确说明是否成功；如果工具提示需要确认、已有读数或已有账单，要如实提醒用户。"
        "如果只是生成账单草稿，必须明确说明草稿未保存，需要用户确认后再操作。"
        f"\n\n今天：{date.today().isoformat()}"
        "\n\n显式业务规则：\n"
        + _domain_rule_summary()
        + ("\n\n结构化意图识别：\n" + json.dumps(intent, ensure_ascii=False, default=str) if intent else "")
        + ("\n\n工具执行计划：\n" + json.dumps(tool_plan, ensure_ascii=False, default=str) if tool_plan else "")
        + "\n\n命中的业务 Skill 文档：\n"
        + skill_context
        + "\n\n实时系统数据快照：\n"
        + data_context
        + ("\n\n上传图片上下文：\n" + image_context if image_context else "")
        + ("\n\n业务会话上下文：\n" + json.dumps(session_context, ensure_ascii=False, default=str) if session_context else "")
        + "\n\n用户当前问题：\n"
        + (prompt or "")
    )


def _collect_bill_images(tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    images = []
    for result in tool_results:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        if data.get("image_type") == "bill_receipt" and data.get("receipt"):
            images.append(data)
        receipt_image = data.get("receipt_image")
        if isinstance(receipt_image, dict) and receipt_image.get("image_type") == "bill_receipt" and receipt_image.get("receipt"):
            images.append(receipt_image)
    return images


def _uploaded_images_from_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    uploaded_images = data.get("uploaded_images")
    if isinstance(uploaded_images, list) and uploaded_images:
        return [item for item in uploaded_images if isinstance(item, dict)]

    history = data.get("history") or []
    for message in reversed(history):
        if not isinstance(message, dict):
            continue
        images = message.get("images")
        if not isinstance(images, list) or not images:
            continue
        result = []
        for idx, image in enumerate(images):
            if not isinstance(image, dict):
                continue
            result.append({
                "image_index": idx,
                "image": image.get("dataUrl") or image.get("image") or "",
                "file_name": image.get("fileName") or image.get("file_name") or "",
                "ocr_number": image.get("ocrNumber") if image.get("ocrNumber") is not None else image.get("ocr_number"),
                "ocr_meter_type": image.get("meterType") or image.get("ocr_meter_type") or image.get("meter_type"),
                "meter_number": image.get("meterNumber") or image.get("meter_number"),
                "building_id": image.get("buildingId") or image.get("building_id"),
                "building_name": image.get("buildingName") or image.get("building_name"),
                "room_id": image.get("roomId") or image.get("room_id"),
                "room_number": image.get("roomNumber") or image.get("room_number"),
                "tenant_id": image.get("tenantId") or image.get("tenant_id"),
                "tenant_name": image.get("tenantName") or image.get("tenant_name"),
            })
        if result:
            return result
    return []


def _image_context_from_data(data: Dict[str, Any]) -> str:
    parts = []
    uploaded_images = _uploaded_images_from_data(data)
    if isinstance(uploaded_images, list) and uploaded_images:
        for idx, item in enumerate(uploaded_images):
            if not isinstance(item, dict):
                continue
            desc = "图片{idx}: 类型 {meter_type}".format(
                idx=idx + 1,
                meter_type=item.get("ocr_meter_type") or item.get("meter_type") or "未知",
            )
            if item.get("ocr_number") is not None:
                desc += "，OCR识别读数 " + str(item.get("ocr_number"))
            else:
                desc += "，OCR未识别到有效读数"
            location = []
            if item.get("building_name"):
                location.append("楼栋 " + str(item.get("building_name")))
            if item.get("room_number"):
                location.append("房间 " + str(item.get("room_number")))
            if item.get("tenant_name"):
                location.append("租客 " + str(item.get("tenant_name")))
            if item.get("meter_number"):
                location.append("表号 " + str(item.get("meter_number")))
            if location:
                desc += "；" + "，".join(location)
            desc += "。调用读数录入工具时可传 image_index=" + str(idx)
            parts.append(desc)
        parts.append("已上传多张表具照片，可在保存读数时按 image_index 写入对应 photo。")
        return "\n".join(parts)

    if data.get("ocr_number") is not None:
        parts.append("OCR识别读数: " + str(data.get("ocr_number")))
    if data.get("ocr_meter_type"):
        parts.append("图片类型: " + str(data.get("ocr_meter_type")))
    if data.get("uploaded_image"):
        parts.append("已上传表具照片，可在保存读数时作为 photo 写入。")
    return "\n".join(parts)


def _pending_actions_context(data: Dict[str, Any]) -> str:
    actions = data.get("pending_actions") or []
    if not isinstance(actions, list) or not actions:
        return ""
    lines = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        preview = _sanitize_tool_message(action.get("preview") or {})
        lines.append(
            "- ID: {id}; 类型: {type}; 说明: {label}; 预览: {preview}".format(
                id=action.get("id", ""),
                type=action.get("type", ""),
                label=action.get("label", ""),
                preview=json.dumps(preview, ensure_ascii=False, default=str),
            )
        )
    return "\n".join(lines)


def _tool_args_with_upload(name: str, raw_args: Any, data: Dict[str, Any]) -> Any:
    if not isinstance(raw_args, str):
        args = raw_args if isinstance(raw_args, dict) else {}
    else:
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except Exception:
            return raw_args
    if name == "meter_reading_save_from_ai":
        uploaded_images = _uploaded_images_from_data(data)
        selected = None
        if isinstance(uploaded_images, list) and uploaded_images:
            image_index = args.get("image_index")
            try:
                idx = int(image_index)
            except Exception:
                idx = -1
            if 0 <= idx < len(uploaded_images) and isinstance(uploaded_images[idx], dict):
                selected = uploaded_images[idx]
            else:
                wanted = str(args.get("meter_type") or "")
                for item in uploaded_images:
                    if not isinstance(item, dict):
                        continue
                    item_type = _normalize_uploaded_meter_type(item.get("ocr_meter_type") or item.get("meter_type"))
                    if wanted and item_type == wanted:
                        selected = item
                        break
                if selected is None:
                    selected = uploaded_images[0] if isinstance(uploaded_images[0], dict) else None

        if selected:
            if selected.get("ocr_number") is not None and args.get("reading") in {None, ""}:
                args["reading"] = selected.get("ocr_number")
            if selected.get("image") and not args.get("photo"):
                args["photo"] = selected.get("image")
            if selected.get("ocr_meter_type") and not args.get("meter_type"):
                args["meter_type"] = _normalize_uploaded_meter_type(selected.get("ocr_meter_type"))
            if selected.get("meter_type") and not args.get("meter_type"):
                args["meter_type"] = _normalize_uploaded_meter_type(selected.get("meter_type"))
            if selected.get("room_number"):
                args["room_number"] = selected.get("room_number")
            if selected.get("building_id"):
                args["building_id"] = selected.get("building_id")
        else:
            if data.get("ocr_number") is not None and args.get("reading") in {None, ""}:
                args["reading"] = data.get("ocr_number")
            if data.get("uploaded_image") and not args.get("photo"):
                args["photo"] = data.get("uploaded_image")
            if data.get("ocr_meter_type") and not args.get("meter_type"):
                args["meter_type"] = _normalize_uploaded_meter_type(data.get("ocr_meter_type"))
    return args


def _parse_tool_args(raw_args: Any) -> Dict[str, Any]:
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args) if raw_args.strip() else {}
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _find_pending_action(action_id: str, pending_actions: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    actions = [a for a in pending_actions if isinstance(a, dict)]
    if action_id:
        for action in actions:
            if action.get("id") == action_id:
                return action
        return None
    return actions[0] if len(actions) == 1 else None


def _confirm_pending_action(raw_args: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    args = _parse_tool_args(raw_args)
    pending_actions = data.get("pending_actions") or []
    action = _find_pending_action(str(args.get("action_id") or ""), pending_actions)
    if not action:
        return {"success": False, "message": "未找到待确认操作，或存在多个待确认操作需要指定。"}
    result = execute_tool(action.get("tool", ""), action.get("args") or {})
    result_data = result.get("data") if isinstance(result, dict) else {}
    success = bool(result.get("ok")) and bool(isinstance(result_data, dict) and result_data.get("success"))
    return {
        "success": success,
        "confirmed_action_id": action.get("id"),
        "clear_pending_action_ids": [action.get("id")] if success else [],
        "execution": result,
        "receipt_image": result_data.get("receipt_image") if isinstance(result_data, dict) else None,
    }


def _cancel_pending_action(raw_args: Any, data: Dict[str, Any]) -> Dict[str, Any]:
    args = _parse_tool_args(raw_args)
    pending_actions = data.get("pending_actions") or []
    action = _find_pending_action(str(args.get("action_id") or ""), pending_actions)
    if not action:
        return {"success": False, "message": "未找到待取消操作，或存在多个待确认操作需要指定。"}
    return {
        "success": True,
        "cancelled_action_id": action.get("id"),
        "clear_pending_action_ids": [action.get("id")],
    }


def _pending_action_followup_suggestions(action: Dict[str, Any], action_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not action_result.get("success") or action.get("type") != "save_meter_reading":
        return []
    preview = action.get("preview") if isinstance(action.get("preview"), dict) else {}
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    building = str(preview.get("building_name") or preview.get("building") or args.get("building_name") or "").strip()
    month = str(preview.get("month") or args.get("month") or "").strip()
    scope = (building + month).strip()
    prompt = "\u7ee7\u7eed\u67e5\u770b" + scope + "\u8fd8\u6709\u54ea\u4e9b\u6c34\u7535\u8868\u6ca1\u6709\u8bfb\u6570" if scope else "\u7ee7\u7eed\u67e5\u770b\u672c\u6708\u8fd8\u6709\u54ea\u4e9b\u6c34\u7535\u8868\u6ca1\u6709\u8bfb\u6570"
    return [
        {
            "label": "\u7ee7\u7eed\u5f55\u5165\u4e0b\u4e00\u5757\u8868",
            "prompt": prompt,
            "description": "\u56de\u5230\u672a\u8bfb\u6570\u6e05\u5355\uff0c\u63a5\u7740\u5904\u7406\u4e0b\u4e00\u95f4\u623f",
        },
        {
            "label": "\u67e5\u770b\u672a\u8bfb\u8868",
            "prompt": prompt,
            "description": "\u5237\u65b0\u5f53\u524d\u672a\u5b8c\u6210\u7684\u6c34\u7535\u8868\u8fdb\u5ea6",
        },
    ]


def _pending_action_command_response(data: Dict[str, Any], command: str) -> Dict[str, Any]:
    pending_actions = data.get("pending_actions") or []
    action_id = str(data.get("pending_action_id") or "")
    action = _find_pending_action(action_id, pending_actions)
    if not action:
        reply = "未找到对应的待确认操作，请重新生成识别结果。"
        session_context = _session_context(data)
        return {
            "reply": reply,
            "bill_images": [],
            "pending_actions": pending_actions,
            "action_result": {"success": False, "message": reply},
            "session_context": session_context,
            "skill_hits": [],
            "suggested_actions": [],
            "response": {"type": "assistant_message", "content": reply, "pending_actions": pending_actions, "bill_images": [], "suggested_actions": [], "action_result": {"success": False, "message": reply}, "session_context": session_context},
        }

    if command == "confirm":
        action_result = _confirm_pending_action({"action_id": action_id}, data)
        action_label = str(action.get("label") or "这项操作")
        execution = action_result.get("execution") or {}
        execution_data = execution.get("data") if isinstance(execution, dict) else {}
        detail = execution_data.get("message") if isinstance(execution_data, dict) else None
        reply = ("已确认并完成：" + action_label) if action_result.get("success") else (detail or GUIDED_HELP_REPLY)
        if action_result.get("success") and action.get("type") == "save_meter_reading" and (action.get("args") or {}).get("photo"):
            if isinstance(execution_data, dict) and execution_data.get("bill_photo_synced"):
                reply += "，表具照片已同步到当前账单。"
            else:
                reply += "，表具照片已保存，后续生成账单时会自动带入。"
    else:
        action_result = _cancel_pending_action({"action_id": action_id}, data)
        reply = "已取消：" + str(action.get("label") or "这项操作")

    if _looks_like_technical_failure(reply):
        reply = GUIDED_HELP_REPLY

    tool_result = {"ok": True, "tool": "ai_pending_action_command", "data": action_result}
    bill_images = _collect_bill_images([tool_result])
    remaining_actions = _merge_pending_actions(pending_actions, [tool_result])
    session_context = _next_session_context(data, [tool_result])
    suggested_actions = _pending_action_followup_suggestions(action, action_result)
    return {
        "reply": reply,
        "bill_images": bill_images,
        "pending_actions": remaining_actions,
        "action_result": action_result,
        "session_context": session_context,
        "skill_hits": [],
        "suggested_actions": suggested_actions,
        "response": {"type": "assistant_message", "content": reply, "pending_actions": remaining_actions, "bill_images": bill_images, "suggested_actions": suggested_actions, "action_result": action_result, "session_context": session_context},
    }


def _merge_pending_actions(existing: List[Dict[str, Any]], tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions = [a for a in (existing or []) if isinstance(a, dict)]
    by_id = {a.get("id"): a for a in actions if a.get("id")}
    for result in tool_results:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        for action_id in data.get("clear_pending_action_ids") or []:
            by_id.pop(action_id, None)
        pending = data.get("pending_action")
        if isinstance(pending, dict) and pending.get("id"):
            by_id[pending["id"]] = pending
    return list(by_id.values())


def _collect_suggested_actions(tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    seen = set()
    for result in tool_results:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        for item in data.get("suggested_actions") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            if not label or not prompt:
                continue
            key = (label, prompt)
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({
                "id": str(item.get("id") or ""),
                "label": label,
                "prompt": prompt,
                "description": str(item.get("description") or "").strip(),
            })
    return suggestions


def _infer_business_suggested_actions(reply: str) -> List[Dict[str, Any]]:
    text = str(reply or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。！？?])|\n+", text) if part.strip()]
    cue_pattern = re.compile(r"要不要|是否|要我|需要我|要现在|现在要|要(?=查看|查询|列出|生成|录入|绑定|发送|提醒|导出|处理|创建|修改|删除|保存|核对|分析)|继续|下一步|可以.{0,12}吗|吗[？?]?$")
    missing_pattern = re.compile(r"请告诉|请提供|请补充|需要补充|哪个|哪一个|哪间|多少|什么时间|具体日期|具体金额|读数是(?:多少|几)")
    action_rules = [
        ("录入读数", re.compile(r"读数|抄表")),
        ("生成账单图片", re.compile(r"账单图片|收据图片")),
        ("生成账单", re.compile(r"账单")),
        ("绑定表具", re.compile(r"绑定.{0,8}(?:水表|电表|表具)|(?:水表|电表|表具).{0,8}绑定")),
        ("录入收款", re.compile(r"收款|交租|缴费")),
        ("继续合同操作", re.compile(r"合同|签约|退租")),
        ("发送账单", re.compile(r"发送|发账单")),
        ("查看详情", re.compile(r"查看|查询|列出|明细|清单|汇总|统计|分析|核对")),
        ("提醒租客", re.compile(r"提醒|通知")),
        ("导出数据", re.compile(r"导出|下载")),
        ("继续处理", re.compile(r"新增|添加|修改|删除|录入|生成|绑定|发送|创建|覆盖|恢复|保存|处理")),
    ]
    for question in reversed(parts):
        cue_match = cue_pattern.search(question)
        if not cue_match or missing_pattern.search(question):
            continue
        action_scope = question[cue_match.start():]
        context = (text[-260:] + " " + question).strip()
        label = ""
        for candidate, pattern in action_rules:
            if pattern.search(action_scope):
                label = candidate
                break
        if not label:
            for candidate, pattern in action_rules:
                if pattern.search(context):
                    label = candidate
                    break
        if not label:
            continue
        action_text = re.sub(
            r"^[^，。！？?]{0,12}?(?:要不要|是否需要|是否|要我|需要我|要现在|现在要)",
            "",
            question,
        ).strip()
        action_text = re.sub(r"[吗呢吧。！？?]+$", "", action_text).strip()
        if not action_text or action_text in {"继续", "继续处理", "下一步"}:
            prompt = "继续刚才建议的业务操作。"
        else:
            prompt = "是的，继续" + action_text + "。"
        return [{
            "id": "auto_business_continue",
            "label": label,
            "prompt": prompt,
            "description": "继续刚才的业务流程",
        }]
    return []


def _collect_form_actions(tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    forms: List[Dict[str, Any]] = []
    seen = set()
    for result in tool_results:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        candidates = []
        if isinstance(data.get("form_action"), dict):
            candidates.append(data.get("form_action"))
        for item in data.get("form_actions") or []:
            if isinstance(item, dict):
                candidates.append(item)
        for form in candidates:
            form_id = str(form.get("id") or "")
            form_type = str(form.get("type") or "")
            key = form_id or form_type or json.dumps(form, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            forms.append(form)
    return forms


def _tool_result_payloads(tool_results: List[Dict[str, Any]]) -> List[tuple[str, Dict[str, Any]]]:
    payloads: List[tuple[str, Dict[str, Any]]] = []
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        tool_name = str(result.get("tool") or "")
        result_data = result.get("data")
        if isinstance(result_data, dict):
            payloads.append((tool_name, result_data))
            execution = result_data.get("execution")
            execution_data = execution.get("data") if isinstance(execution, dict) else None
            if isinstance(execution_data, dict):
                payloads.append((str(execution.get("tool") or ""), execution_data))
    return payloads


def _next_session_context(data: Dict[str, Any], tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    context = _session_context(data)
    prompt = str(data.get("prompt") or "").strip()
    intent = _detect_intent(data)
    workflow = str(intent.get("workflow") or "")
    if workflow:
        previous_workflow = context.get("active_workflow")
        if previous_workflow == "contract_create" and workflow != "contract_create":
            context["suspended_contract"] = {
                key: context.get(key)
                for key in ("building_id", "building_name", "room_id", "room_number", "contract_draft")
                if context.get(key) is not None and context.get(key) != ""
            }
        if workflow == "contract_create" and isinstance(context.get("suspended_contract"), dict):
            suspended = context.get("suspended_contract") or {}
            for key in ("building_id", "building_name", "room_id", "room_number", "contract_draft"):
                if suspended.get(key) is not None and suspended.get(key) != "":
                    context[key] = suspended.get(key)
        context["active_workflow"] = workflow
        if workflow != "contract_create":
            context.pop("contract_draft", None)

    building_hint = _known_building_hint(prompt)
    if building_hint:
        context.update(building_hint)
    room_number = _room_number_hint(prompt)
    if room_number:
        context["room_number"] = room_number
        context.pop("room_id", None)

    for tool_name, payload in _tool_result_payloads(tool_results):
        if tool_name == "contract_create_from_ai":
            context["active_workflow"] = "contract_create"
            draft = context.get("contract_draft")
            draft = dict(draft) if isinstance(draft, dict) else {}
            form_action = payload.get("form_action")
            form_values = form_action.get("values") if isinstance(form_action, dict) else None
            if isinstance(form_values, dict):
                draft.update(form_values)
            contract = payload.get("contract")
            if isinstance(contract, dict):
                draft.update(contract)
            room = payload.get("room")
            if isinstance(room, dict):
                context["room_id"] = room.get("id")
                context["room_number"] = room.get("room_number")
                context["building_id"] = room.get("building_id")
                context["building_name"] = room.get("building_name")
                draft["room_id"] = room.get("id")
                draft["room_number"] = room.get("room_number")
                draft["building_id"] = room.get("building_id")
                draft["building_name"] = room.get("building_name")
            tenant = payload.get("tenant")
            if isinstance(tenant, dict):
                draft["tenant_id"] = tenant.get("id")
                draft["tenant_name"] = tenant.get("name")
            if building_hint:
                draft.update(building_hint)
            if room_number:
                draft["room_number"] = room_number
            context["contract_draft"] = draft
        elif tool_name == "confirm_create_contract" and payload.get("success"):
            created = payload.get("contract")
            if isinstance(created, dict):
                context["building_name"] = created.get("building_name") or context.get("building_name")
                context["room_number"] = created.get("room_number") or context.get("room_number")
            context["active_workflow"] = "contract_create"
            context["last_completed_workflow"] = "contract_create"
            context.pop("room_id", None)
            context.pop("room_number", None)
            context.pop("contract_draft", None)
            context.pop("suspended_contract", None)
        elif tool_name.startswith("meter_reading_") or tool_name == "confirm_save_meter_reading":
            context["active_workflow"] = "meter_reading"

    context["thread_id"] = _thread_id(data)
    context["last_intent"] = intent
    context["tool_plan"] = _tool_plan_for_intent(intent, data)
    context["workflow_state"] = _workflow_state_from_data({**data, "session_context": context}, intent, tool_results)
    return {key: value for key, value in context.items() if value is not None and value != ""}


def _prepare_chat_context(data: Dict[str, Any], prompt: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    intent = _detect_intent(data)
    tool_plan = _tool_plan_for_intent(intent, data)
    workflow_state = _workflow_state_from_data(data, intent, [])
    skill_hits = search_skills(prompt, top_k=5)
    skill_context = format_skill_hits(skill_hits)
    data_context = build_rental_ai_context(prompt)
    image_context = _image_context_from_data(data)
    pending_context = _pending_actions_context(data)
    merged_image_context = image_context
    if pending_context:
        merged_image_context = (merged_image_context + "\n\n待确认操作：\n" + pending_context).strip()
    session_context = _session_context(data)
    system_prompt = _build_system_prompt(
        prompt,
        skill_context,
        data_context,
        merged_image_context,
        session_context,
        intent,
        tool_plan,
    )

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": prompt})

    tools = get_tool_schemas() + PENDING_ACTION_TOOLS
    return {
        "messages": messages,
        "tools": tools,
        "skill_hits": skill_hits,
        "intent": intent,
        "workflow_state": workflow_state,
        "tool_plan": tool_plan,
    }


def _execute_ai_tool_call(raw_call: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    call = _extract_tool_call(raw_call)
    if call["name"] == "ai_suggest_actions":
        args = _parse_tool_args(call["arguments"])
        return {"ok": True, "tool": call["name"], "data": {"suggested_actions": args.get("actions") or []}}
    if call["name"] == "ai_confirm_pending_action":
        return {"ok": True, "tool": call["name"], "data": _confirm_pending_action(call["arguments"], data)}
    if call["name"] == "ai_cancel_pending_action":
        return {"ok": True, "tool": call["name"], "data": _cancel_pending_action(call["arguments"], data)}
    tool_args = _tool_args_with_upload(call["name"], call["arguments"], data)
    if call["name"] == "contract_create_from_ai" and isinstance(tool_args, dict):
        prompt = str(data.get("prompt") or "")
        merged_args = {**_contract_create_args(data), **tool_args}
        building_hint = _known_building_hint(prompt)
        if building_hint:
            merged_args.update(building_hint)
        room_number = _room_number_hint(prompt)
        if room_number:
            merged_args["room_number"] = room_number
            merged_args.pop("room_id", None)
        tool_args = merged_args
    if call["name"] == "meter_reading_save_from_ai" and isinstance(tool_args, dict):
        prompt = str(data.get("prompt") or "")
        context = _session_context(data)
        merged_args = dict(tool_args)
        for key, value in _context_location_fields(context).items():
            if value not in {None, ""} and key not in merged_args:
                merged_args[key] = value
        month = _month_hint(prompt) or str(merged_args.get("month") or "").strip()
        if month:
            merged_args["month"] = month
        readings = _extract_meter_reading_values(prompt)
        if readings.get("water") and str(merged_args.get("meter_type") or "") in {"", "water"} and "reading" not in merged_args:
            merged_args["reading"] = readings["water"]
            merged_args["meter_type"] = "water"
        if readings.get("electric") and str(merged_args.get("meter_type") or "") == "electric" and "reading" not in merged_args:
            merged_args["reading"] = readings["electric"]
        if "reading" not in merged_args:
            if str(merged_args.get("meter_type") or "") == "water" and readings.get("water"):
                merged_args["reading"] = readings["water"]
            elif str(merged_args.get("meter_type") or "") == "electric" and readings.get("electric"):
                merged_args["reading"] = readings["electric"]
        tool_args = merged_args
    return execute_tool(call["name"], tool_args)


def _append_tool_round(
    messages: List[Dict[str, Any]],
    resp: Dict[str, Any],
    data: Dict[str, Any],
) -> Dict[str, Any]:
    tool_calls = resp.get("tool_calls") or []
    next_messages = list(messages)
    next_messages.append({
        "role": "assistant",
        "content": resp.get("content") or "",
        "tool_calls": tool_calls,
    })
    results: List[Dict[str, Any]] = []
    for raw_call in tool_calls:
        call = _extract_tool_call(raw_call)
        result = _execute_ai_tool_call(raw_call, data)
        results.append(result)
        next_messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "name": call["name"],
            "content": _json_for_tool(result),
        })
    return {"messages": next_messages, "tool_results": results}


def _finalize_chat_response(
    reply: str,
    data: Dict[str, Any],
    last_tool_results: List[Dict[str, Any]],
    skill_hits: List[Dict[str, Any]],
) -> Dict[str, Any]:
    bill_images = _collect_bill_images(last_tool_results)
    pending_actions = _merge_pending_actions(data.get("pending_actions") or [], last_tool_results)
    suggested_actions = _collect_suggested_actions(last_tool_results)
    form_actions = _collect_form_actions(last_tool_results)
    session_context = _next_session_context(data, last_tool_results)
    intent = session_context.get("last_intent") if isinstance(session_context.get("last_intent"), dict) else _detect_intent({**data, "session_context": session_context})
    tool_plan = session_context.get("tool_plan") if isinstance(session_context.get("tool_plan"), dict) else _tool_plan_for_intent(intent, data)
    workflow_state = session_context.get("workflow_state") if isinstance(session_context.get("workflow_state"), dict) else _workflow_state_from_data({**data, "session_context": session_context}, intent, last_tool_results)
    has_bill_confirmation = any(
        isinstance(action, dict) and action.get("type") == "create_bill"
        for action in pending_actions
    )
    has_contract_update = any(
        isinstance(action, dict) and action.get("type") in {"update_contract", "create_contract"}
        for action in pending_actions
    )
    has_payment_confirmation = any(
        isinstance(action, dict) and action.get("type") == "record_payment"
        for action in pending_actions
    )

    if _has_internal_tool_failure(last_tool_results) or _looks_like_technical_failure(reply):
        reply = GUIDED_HELP_REPLY
    elif form_actions:
        reply = "还需要补充一些合同信息，请在下方表单填写后提交。"
    elif has_bill_confirmation:
        reply = "账单草稿已准备，请核对金额和旧账单信息，并使用卡片按钮确认或取消。"
    elif has_contract_update:
        reply = "合同内容已准备，请核对下方的变更前后信息，并使用卡片按钮确认或取消。"
    elif has_payment_confirmation:
        reply = "收款信息已准备，请核对账单、金额和日期，并使用卡片按钮确认或取消。"
    elif not reply and bill_images:
        reply = "账单图片已生成，可在下方预览、复制或保存。"
    elif not reply and last_tool_results:
        reply = "我已经拿到相关数据，但还不确定你希望继续查询、录入还是生成账单。请告诉我你想完成的下一步。"
    if bill_images and "账单图片" not in reply and "收据图片" not in reply:
        reply = (reply.rstrip() + "\n\n账单图片已生成，可在下方预览、复制或保存。").strip()
    if not reply:
        reply = GUIDED_HELP_REPLY
    if not suggested_actions and not pending_actions and not form_actions:
        suggested_actions = _infer_business_suggested_actions(reply)

    return {
        "reply": reply,
        "bill_images": bill_images,
        "pending_actions": pending_actions,
        "suggested_actions": suggested_actions,
        "form_actions": form_actions,
        "session_context": session_context,
        "intent": intent,
        "tool_plan": tool_plan,
        "workflow_state": workflow_state,
        "response": {"type": "assistant_message", "content": reply, "pending_actions": pending_actions, "bill_images": bill_images, "suggested_actions": suggested_actions, "form_actions": form_actions, "session_context": session_context, "intent": intent, "tool_plan": tool_plan, "workflow_state": workflow_state},
        "skill_hits": [{
            "skill": hit.get("skill"),
            "title": hit.get("title"),
            "backend": hit.get("backend"),
            "score": hit.get("score"),
        } for hit in skill_hits],
    }


def _chat_linear(data: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    history = data.get("history") or []
    pending_action_command = str(data.get("pending_action_command") or "").strip().lower()
    if pending_action_command in {"confirm", "cancel"}:
        return _pending_action_command_response(data, pending_action_command)
    if not prompt:
        return {"reply": "请先输入你想查询的问题。"}
    meter_fallback = _meter_reading_fallback(data)
    if meter_fallback:
        return meter_fallback

    context = _prepare_chat_context(data, prompt, history)
    messages = context["messages"]
    tools = context["tools"]
    skill_hits = context["skill_hits"]
    last_tool_results: List[Dict[str, Any]] = []
    resp = ai_svc.call_with_tools(messages, tools=tools, max_tokens=1200, temperature=0.2)
    max_tool_rounds = int((context.get("tool_plan") or {}).get("max_tool_rounds") or 2)

    for _ in range(max_tool_rounds):
        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            break
        round_result = _append_tool_round(messages, resp, data)
        messages = round_result["messages"]
        last_tool_results.extend(round_result["tool_results"])
        resp = ai_svc.call_with_tools(messages, tools=tools, max_tokens=1200, temperature=0.2)

    return _finalize_chat_response(resp.get("content") or "", data, last_tool_results, skill_hits)


def _graph_route(state: AIChatGraphState) -> str:
    command = str(state.get("pending_action_command") or "").strip().lower()
    if command in {"confirm", "cancel"}:
        return "pending_command"
    if not str(state.get("prompt") or "").strip():
        return "empty_prompt"
    data = state.get("data") or {}
    intent = _detect_intent(data)
    workflow = str(intent.get("workflow") or "")
    _trace_state(state, "route", {"intent": intent})
    if workflow == "meter_reading" and _meter_reading_fallback_args(data):
        return "meter_reading"
    if workflow == "contract_create" and _should_fallback_contract_create(data):
        return "contract_form"
    return "normal_chat"


def _graph_pending_command_node(state: AIChatGraphState) -> AIChatGraphState:
    _trace_state(state, "pending_command", {"command": state.get("pending_action_command")})
    return {
        "result": _pending_action_command_response(
            state.get("data") or {},
            str(state.get("pending_action_command") or "").strip().lower(),
        )
    }


def _graph_empty_prompt_node(state: AIChatGraphState) -> AIChatGraphState:
    _trace_state(state, "empty_prompt", {})
    session_context = _session_context(state.get("data") or {})
    return {"result": {"reply": "请先输入你想查询的问题。", "session_context": session_context, "response": {"type": "assistant_message", "content": "请先输入你想查询的问题。", "session_context": session_context}}}


def _graph_contract_form_node(state: AIChatGraphState) -> AIChatGraphState:
    data = state.get("data") or {}
    intent = _detect_intent(data)
    _trace_state(state, "contract_form", {"intent": intent, "args": _contract_create_args(data)})
    return {"result": _contract_create_form_fallback(data) or _chat_linear(data)}


def _graph_meter_reading_node(state: AIChatGraphState) -> AIChatGraphState:
    data = state.get("data") or {}
    _trace_state(state, "meter_reading", {"prompt": data.get("prompt"), "session_context": _session_context(data)})
    return {"result": _meter_reading_fallback(data) or _chat_linear(data)}


def _graph_prepare_context_node(state: AIChatGraphState) -> AIChatGraphState:
    context = _prepare_chat_context(
        state.get("data") or {},
        str(state.get("prompt") or "").strip(),
        state.get("history") or [],
    )
    _trace_state(state, "prepare_context", {
        "intent": context.get("intent"),
        "workflow_state": context.get("workflow_state"),
        "tool_plan": context.get("tool_plan"),
    })
    return {
        "messages": context["messages"],
        "tools": context["tools"],
        "skill_hits": context["skill_hits"],
        "intent": context.get("intent") or {},
        "workflow_state": context.get("workflow_state") or {},
        "tool_plan": context.get("tool_plan") or {},
        "last_tool_results": [],
        "tool_round": 0,
    }


def _graph_call_model_node(state: AIChatGraphState) -> AIChatGraphState:
    resp = ai_svc.call_with_tools(
        state.get("messages") or [],
        tools=state.get("tools") or [],
        max_tokens=1200,
        temperature=0.2,
    )
    _trace_state(state, "call_model", {
        "tool_round": state.get("tool_round") or 0,
        "tool_calls": [
            _extract_tool_call(call).get("name")
            for call in (resp.get("tool_calls") or [])
            if isinstance(call, dict)
        ],
        "content_preview": str(resp.get("content") or "")[:160],
    })
    return {"model_response": resp}


def _graph_should_run_tools(state: AIChatGraphState) -> str:
    resp = state.get("model_response") or {}
    tool_calls = resp.get("tool_calls") or []
    tool_round = int(state.get("tool_round") or 0)
    max_rounds = int((state.get("tool_plan") or {}).get("max_tool_rounds") or 2)
    if tool_calls and tool_round < max_rounds:
        return "run_tools"
    return "finalize"


def _graph_run_tools_node(state: AIChatGraphState) -> AIChatGraphState:
    round_result = _append_tool_round(
        state.get("messages") or [],
        state.get("model_response") or {},
        state.get("data") or {},
    )
    _trace_state(state, "run_tools", {
        "tool_round": int(state.get("tool_round") or 0) + 1,
        "results": [
            {"tool": result.get("tool"), "ok": result.get("ok")}
            for result in round_result["tool_results"]
            if isinstance(result, dict)
        ],
    })
    return {
        "messages": round_result["messages"],
        "last_tool_results": (state.get("last_tool_results") or []) + round_result["tool_results"],
        "tool_round": int(state.get("tool_round") or 0) + 1,
    }


def _graph_finalize_node(state: AIChatGraphState) -> AIChatGraphState:
    resp = state.get("model_response") or {}
    result = _finalize_chat_response(
        resp.get("content") or "",
        state.get("data") or {},
        state.get("last_tool_results") or [],
        state.get("skill_hits") or [],
    )
    _trace_state(state, "finalize", {
        "reply": result.get("reply"),
        "intent": result.get("intent"),
        "workflow_state": result.get("workflow_state"),
    })
    return {"result": result}


def _get_chat_graph() -> Any:
    global _CHAT_GRAPH
    if StateGraph is None or START is None or END is None:
        return None
    if _CHAT_GRAPH is not None:
        return _CHAT_GRAPH

    graph = StateGraph(AIChatGraphState)
    graph.add_node("route", lambda state: {})
    graph.add_node("pending_command", _graph_pending_command_node)
    graph.add_node("empty_prompt", _graph_empty_prompt_node)
    graph.add_node("contract_form", _graph_contract_form_node)
    graph.add_node("meter_reading", _graph_meter_reading_node)
    graph.add_node("prepare_context", _graph_prepare_context_node)
    graph.add_node("call_model", _graph_call_model_node)
    graph.add_node("run_tools", _graph_run_tools_node)
    graph.add_node("finalize", _graph_finalize_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        _graph_route,
        {
            "pending_command": "pending_command",
            "empty_prompt": "empty_prompt",
            "contract_form": "contract_form",
            "meter_reading": "meter_reading",
            "normal_chat": "prepare_context",
        },
    )
    graph.add_edge("pending_command", END)
    graph.add_edge("empty_prompt", END)
    graph.add_edge("contract_form", END)
    graph.add_edge("meter_reading", END)
    graph.add_edge("prepare_context", "call_model")
    graph.add_conditional_edges(
        "call_model",
        _graph_should_run_tools,
        {
            "run_tools": "run_tools",
            "finalize": "finalize",
        },
    )
    graph.add_edge("run_tools", "call_model")
    graph.add_edge("finalize", END)
    _CHAT_GRAPH = graph.compile(checkpointer=_CHAT_CHECKPOINTER)
    return _CHAT_GRAPH


def _chat_graph(data: Dict[str, Any]) -> Dict[str, Any]:
    graph = _get_chat_graph()
    if graph is None:
        return _chat_linear(data)
    thread_id = _thread_id(data)
    _trace_thread(thread_id, "graph_start", {"prompt": data.get("prompt"), "session_context": _session_context(data)})
    result = graph.invoke({
        "data": data,
        "thread_id": thread_id,
        "prompt": str(data.get("prompt") or "").strip(),
        "history": data.get("history") or [],
        "pending_action_command": str(data.get("pending_action_command") or "").strip().lower(),
    }, config={"configurable": {"thread_id": thread_id}})
    graph_result = result.get("result") if isinstance(result, dict) else None
    return graph_result if isinstance(graph_result, dict) else _chat_linear(data)


def chat(data: Dict[str, Any]) -> Dict[str, Any]:
    data = _hydrate_thread_data(data)
    result = _chat_graph(data)
    _persist_thread_state(_thread_id(data), result)
    _trace_thread(_thread_id(data), "graph_end", {
        "reply": result.get("reply") if isinstance(result, dict) else "",
        "intent": result.get("intent") if isinstance(result, dict) else {},
        "workflow_state": result.get("workflow_state") if isinstance(result, dict) else {},
    })
    return result
