# -*- coding: utf-8 -*-
"""AIChat 的 Skill 编排器。

流程：
1. 用 Skill.md 做语义检索，给模型明确业务能力边界。
2. 暴露白名单工具，让模型按需查询实时业务数据。
3. 工具执行后再让模型生成最终回答。
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

from ai_service import ai_svc

from app.services.ai_context import build_rental_ai_context
from app.services.skill_executor import execute_tool, get_tool_schemas
from app.services.skill_registry import format_skill_hits
from app.services.skill_vector_store import search_skills


PENDING_ACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ai_confirm_pending_action",
            "description": "确认并执行一个待确认操作，例如录入读数或保存账单。",
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


def _build_system_prompt(prompt: str, skill_context: str, data_context: str, image_context: str = "") -> str:
    return (
        "你是租房管理系统助手，名叫“租房小管家”。"
        "你需要用中文回答，简洁、准确、可执行。"
        "优先使用工具查询实时业务数据；工具结果比推测更可靠。"
        "不要编造房间、租客、账单、读数、收款记录。"
        "如果数据没有录入或上下文没有提供，要明确说明缺少什么。"
        "涉及金额时使用人民币并保留两位小数。"
        "读数只返回数字，不附带单位。"
        "展示格式要适合聊天窗口：首行先给结论，后面用简短分组和紧凑表格。"
        "不要频繁使用 Markdown 大标题、横线和表情符号；除非确实需要，不要输出 ##、---。"
        "当用户要求输出、生成、查看、复制账单图片或收据图片时，优先调用 bill_get_receipt_image_data。"
        "如果工具返回了账单图片数据，文字回复只需要简短说明已生成图片，不要再重复大段账单明细。"
        "当用户上传水表或电表图片，并要求录入读数时，调用 meter_reading_save_from_ai。"
        "当用户继续要求生成账单时，在读数保存成功后调用 bill_create_from_ai。"
        "如果缺少房间号、月份或水表/电表类型，不要猜测，先请用户补充。"
        "如果存在待确认操作，且用户回复确认、可以、录入、保存、执行，就调用 ai_confirm_pending_action。"
        "如果用户要求取消待确认操作，就调用 ai_cancel_pending_action。"
        "除 meter_reading_save_from_ai 和 bill_create_from_ai 这两个白名单工具外，不能声称已经写入、发送账单、确认收款、修改合同或覆盖读数。"
        "保存读数或生成账单后，要根据工具结果明确说明是否成功；如果工具提示需要确认、已有读数或已有账单，要如实提醒用户。"
        "如果只是生成账单草稿，必须明确说明草稿未保存，需要用户确认后再操作。"
        f"\n\n今天：{date.today().isoformat()}"
        "\n\n命中的业务 Skill 文档：\n"
        + skill_context
        + "\n\n实时系统数据快照：\n"
        + data_context
        + ("\n\n上传图片上下文：\n" + image_context if image_context else "")
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


def _image_context_from_data(data: Dict[str, Any]) -> str:
    parts = []
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
        if data.get("ocr_number") is not None and args.get("reading") in {None, ""}:
            args["reading"] = data.get("ocr_number")
        if data.get("uploaded_image") and not args.get("photo"):
            args["photo"] = data.get("uploaded_image")
        if data.get("ocr_meter_type") and not args.get("meter_type"):
            meter_type = str(data.get("ocr_meter_type"))
            args["meter_type"] = "water" if "水" in meter_type else "electric"
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
    return {
        "success": bool(result.get("ok")) and bool(isinstance(result_data, dict) and result_data.get("success")),
        "confirmed_action_id": action.get("id"),
        "clear_pending_action_ids": [action.get("id")],
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


def chat(data: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(data.get("prompt") or "").strip()
    history = data.get("history") or []
    if not prompt:
        return {"reply": "请先输入你想查询的问题。"}

    skill_hits = search_skills(prompt, top_k=5)
    skill_context = format_skill_hits(skill_hits)
    data_context = build_rental_ai_context(prompt)
    image_context = _image_context_from_data(data)
    pending_context = _pending_actions_context(data)
    merged_image_context = image_context
    if pending_context:
        merged_image_context = (merged_image_context + "\n\n待确认操作：\n" + pending_context).strip()
    system_prompt = _build_system_prompt(prompt, skill_context, data_context, merged_image_context)

    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": prompt})

    tools = get_tool_schemas() + PENDING_ACTION_TOOLS
    last_tool_results: List[Dict[str, Any]] = []
    resp = ai_svc.call_with_tools(messages, tools=tools, max_tokens=1200, temperature=0.2)

    for _ in range(2):
        tool_calls = resp.get("tool_calls") or []
        if not tool_calls:
            break

        messages.append({
            "role": "assistant",
            "content": resp.get("content") or "",
            "tool_calls": tool_calls,
        })

        for raw_call in tool_calls:
            call = _extract_tool_call(raw_call)
            if call["name"] == "ai_confirm_pending_action":
                result = {"ok": True, "tool": call["name"], "data": _confirm_pending_action(call["arguments"], data)}
            elif call["name"] == "ai_cancel_pending_action":
                result = {"ok": True, "tool": call["name"], "data": _cancel_pending_action(call["arguments"], data)}
            else:
                tool_args = _tool_args_with_upload(call["name"], call["arguments"], data)
                result = execute_tool(call["name"], tool_args)
            last_tool_results.append(result)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": _json_for_tool(result),
            })

        resp = ai_svc.call_with_tools(messages, tools=tools, max_tokens=1200, temperature=0.2)

    reply = resp.get("content") or ""
    bill_images = _collect_bill_images(last_tool_results)
    pending_actions = _merge_pending_actions(data.get("pending_actions") or [], last_tool_results)

    if not reply and bill_images:
        reply = "账单图片已生成，可在下方预览、复制或保存。"
    elif not reply and last_tool_results:
        reply = "我已经查询到相关数据，但 AI 服务没有生成最终文本。工具结果如下：\n```json\n" + _json_for_tool({"results": last_tool_results}, 4000) + "\n```"
    if bill_images and "账单图片" not in reply and "收据图片" not in reply:
        reply = (reply.rstrip() + "\n\n账单图片已生成，可在下方预览、复制或保存。").strip()
    if not reply:
        reply = "抱歉，AI 服务暂时不可用。"

    return {
        "reply": reply,
        "bill_images": bill_images,
        "pending_actions": pending_actions,
        "skill_hits": [{
            "skill": hit.get("skill"),
            "title": hit.get("title"),
            "backend": hit.get("backend"),
            "score": hit.get("score"),
        } for hit in skill_hits],
    }
