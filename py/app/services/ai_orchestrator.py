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
        "不要向用户展示程序错误、接口错误、工具名称、异常堆栈或内部日志。"
        "当无法判断该调用哪个工具、工具没有完成或信息不足时，要追问用户正在做什么、涉及的楼栋房间月份、卡在哪一步，并告诉用户补充后可以继续处理。"
        "如果数据没有录入或上下文没有提供，要明确说明缺少什么。"
        "涉及金额时使用人民币并保留两位小数。"
        "读数只返回数字，不附带单位。"
        "展示格式要适合聊天窗口：首行先给结论，后面用简短分组和紧凑表格。"
        "不要频繁使用 Markdown 大标题、横线和表情符号；除非确实需要，不要输出 ##、---。"
        "当用户要求输出、生成、查看、复制账单图片或收据图片时，优先调用 bill_get_receipt_image_data。"
        "如果工具返回了账单图片数据，文字回复只需要简短说明已生成图片，不要再重复大段账单明细。"
        "当用户上传水表或电表图片，并要求录入读数时，调用 meter_reading_save_from_ai。"
        "即使该月份已经存在相同读数，只要用户上传了新照片并要求录入，也要调用 meter_reading_save_from_ai 生成更新确认事项，以便保存照片，不能只回复无需重复录入。"
        "上传图片上下文中的类型、读数、表号、楼栋、房间和租客是结构化识别结果；优先使用这些值，不要重新猜测。"
        "涉及图片识别、录入读数或保存账单时，先返回待确认操作，不能因为用户上传图片就直接写入数据库。"
        "当用户继续要求生成账单时，在读数保存成功后调用 bill_create_from_ai。"
        "用户要求添加网费、卫生费等其他费用时，调用 bill_create_from_ai 并通过 other_fee_details 按项目名称和金额逐项传递，不能只传其他费用汇总。"
        "用户明确要求修改、替换或覆盖已有账单及账单图片时，调用 bill_create_from_ai 并设置 overwrite=true；仍需先返回覆盖确认事项，确认后再更新账单和图片。"
        "如果缺少房间号、月份或水表/电表类型，不要猜测，先请用户补充。"
        "当用户要求修改现有合同的月租、水电单价、保证金、合同日期或水电表绑定时，调用 contract_update_from_ai。"
        "合同修改必须先返回待确认操作；如果同一房间号存在于多个楼栋，要先请用户明确楼栋。"
        "退租、恢复合同、变更租客或更换房间不是普通合同字段修改，不能调用 contract_update_from_ai，需明确告诉用户应使用对应业务流程。"
        "如果存在待确认操作，且用户通过文字表示确认、可以、录入、保存、执行，就调用 ai_confirm_pending_action；界面按钮会通过同一待确认协议直接执行。"
        "如果用户要求取消待确认操作，就调用 ai_cancel_pending_action。"
        "除 meter_reading_save_from_ai、bill_create_from_ai 和 contract_update_from_ai 这三个待确认工具外，不能声称已经写入、发送账单、确认收款、修改合同或覆盖读数。"
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


def _pending_action_command_response(data: Dict[str, Any], command: str) -> Dict[str, Any]:
    pending_actions = data.get("pending_actions") or []
    action_id = str(data.get("pending_action_id") or "")
    action = _find_pending_action(action_id, pending_actions)
    if not action:
        reply = "未找到对应的待确认操作，请重新生成识别结果。"
        return {
            "reply": reply,
            "bill_images": [],
            "pending_actions": pending_actions,
            "skill_hits": [],
            "response": {"type": "assistant_message", "content": reply, "pending_actions": pending_actions, "bill_images": []},
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
    return {
        "reply": reply,
        "bill_images": bill_images,
        "pending_actions": remaining_actions,
        "skill_hits": [],
        "response": {"type": "assistant_message", "content": reply, "pending_actions": remaining_actions, "bill_images": bill_images},
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
    pending_action_command = str(data.get("pending_action_command") or "").strip().lower()
    if pending_action_command in {"confirm", "cancel"}:
        return _pending_action_command_response(data, pending_action_command)
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
    has_contract_update = any(
        isinstance(action, dict) and action.get("type") == "update_contract"
        for action in pending_actions
    )

    if _has_internal_tool_failure(last_tool_results) or _looks_like_technical_failure(reply):
        reply = GUIDED_HELP_REPLY
    elif has_contract_update:
        reply = "合同修改内容已准备，请核对下方的变更前后信息，并使用卡片按钮确认或取消。"
    elif not reply and bill_images:
        reply = "账单图片已生成，可在下方预览、复制或保存。"
    elif not reply and last_tool_results:
        reply = "我已经拿到相关数据，但还不确定你希望继续查询、录入还是生成账单。请告诉我你想完成的下一步。"
    if bill_images and "账单图片" not in reply and "收据图片" not in reply:
        reply = (reply.rstrip() + "\n\n账单图片已生成，可在下方预览、复制或保存。").strip()
    if not reply:
        reply = GUIDED_HELP_REPLY

    return {
        "reply": reply,
        "bill_images": bill_images,
        "pending_actions": pending_actions,
        "response": {"type": "assistant_message", "content": reply, "pending_actions": pending_actions, "bill_images": bill_images},
        "skill_hits": [{
            "skill": hit.get("skill"),
            "title": hit.get("title"),
            "backend": hit.get("backend"),
            "score": hit.get("score"),
        } for hit in skill_hits],
    }
