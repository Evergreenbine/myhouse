# -*- coding: utf-8 -*-
"""业务 Skill 工具执行层。

查询能力直接执行；会改变业务数据的工具必须先返回待确认操作，再由用户确认执行。
"""
from __future__ import annotations

import inspect
import html as html_lib
import json
import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import local_db as db


STATUS_LABELS = {
    "empty": "未录入",
    "draft": "录入中",
    "pending": "待发送",
    "pending_payment": "待收款",
    "unpaid": "待收款",
    "partial": "部分收款",
    "paid": "已收款",
    "recorded": "已录入",
    "missing": "未录入",
}

METER_TYPE_LABELS = {
    "water": "水表",
    "electric": "电表",
}

WATER_COST_PRICE = 2.1
ELECTRIC_COST_PRICE = 0.6

_UNSET = object()

CONTRACT_UPDATE_LABELS = {
    "start_date": "合同开始",
    "end_date": "合同结束",
    "monthly_rent": "月租",
    "water_unit_price": "水费单价",
    "electric_unit_price": "电费单价",
    "deposit": "保证金",
    "water_meter_id": "水表绑定",
    "electric_meter_id": "电表绑定",
    "other_fee_details": "其它费用",
}

ROOM_UPDATE_LABELS = {
    "building_id": "楼栋",
    "room_number": "房间号",
    "room_type": "户型",
    "floor": "楼层",
    "status": "状态",
}

METER_UPDATE_LABELS = {
    "room_id": "所属房间",
    "type": "表具类型",
    "meter_no": "表号",
    "init_reading": "初始读数",
    "photo": "照片",
}


def _money(value: Any) -> str:
    return f"{_num(value):.2f}"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是", "覆盖"}


def _normalize_other_fee_details(value: Any, fallback_amount: Any = 0) -> List[Dict[str, Any]]:
    parsed = value
    if isinstance(value, str):
        try:
            stripped = value.strip()
            parsed = json.loads(stripped) if stripped.startswith(("[", "{")) else stripped
        except Exception:
            parsed = value.strip()
    if isinstance(parsed, dict):
        parsed = [parsed]
    if isinstance(parsed, str):
        text = parsed.strip()
        pairs = re.findall(r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z_-]{0,12})\s*(?:费|费用)?\s*[:：=]?\s*(\d+(?:\.\d+)?)", text)
        parsed = [{"name": name if name.endswith("费") else name + "费", "amount": amount} for name, amount in pairs]
    if not isinstance(parsed, list):
        parsed = []

    details = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("project_name") or "").strip()
        amount = round(_num(item.get("amount")), 2)
        if name and amount > 0:
            details.append({"name": name, "amount": amount})

    fallback = round(_num(fallback_amount), 2)
    if not details and fallback > 0:
        details.append({"name": "其他费用", "amount": fallback})
    return details


def _other_fee_details_text(value: Any) -> str:
    details = _normalize_other_fee_details(value)
    if not details:
        return "无"
    return "、".join(f"{item['name']} ¥{_money(item['amount'])}" for item in details)


def _contract_other_fee_details(contract: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _normalize_other_fee_details(contract.get("other_fee_details"))


def _contract_other_fee_total(contract: Dict[str, Any]) -> float:
    return round(sum(_num(item.get("amount")) for item in _contract_other_fee_details(contract)), 2)


def _normalize_other_fee_names(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value.strip().startswith(("[", "{")) else value
        except Exception:
            parsed = value
    if isinstance(parsed, dict):
        parsed = [parsed]
    elif not isinstance(parsed, list):
        parsed = re.split(r"[,，、\s]+", str(parsed))

    names: List[str] = []
    for item in parsed:
        if isinstance(item, dict):
            raw = item.get("name") or item.get("project_name") or item.get("label") or ""
        else:
            raw = item
        name = str(raw or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _fee_name_key(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).lower()


def _is_clear_other_fee_request(names: List[str], clear_flag: Any) -> bool:
    if _bool(clear_flag):
        return True
    clear_words = {"全部", "所有", "清空", "全部删除", "全删", "全部其它费用", "全部其他费用", "其他费用", "其它费用"}
    clear_keys = {_fee_name_key(word) for word in clear_words}
    return bool(names) and all(_fee_name_key(name) in clear_keys for name in names)


def _matches_other_fee_name(fee_name: Any, remove_name: Any) -> bool:
    fee_key = _fee_name_key(fee_name)
    remove_key = _fee_name_key(remove_name)
    if not fee_key or not remove_key:
        return False
    if fee_key == remove_key:
        return True
    return len(remove_key) >= 2 and (remove_key in fee_key or fee_key in remove_key)


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _pending_action_id(action_type: str, payload: Dict[str, Any]) -> str:
    raw = json.dumps({"type": action_type, "payload": payload}, ensure_ascii=False, sort_keys=True, default=str)
    return action_type + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _pending_action(action_type: str, label: str, tool: str, args: Dict[str, Any], preview: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": _pending_action_id(action_type, args),
        "type": action_type,
        "label": label,
        "tool": tool,
        "args": args,
        "preview": preview,
    }


def _today_month() -> str:
    return date.today().strftime("%Y-%m")


def _shift_month(month: str, offset: int) -> str:
    year, mon = [int(x) for x in month[:7].split("-")]
    idx = year * 12 + mon - 1 + offset
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def _normalize_month(month: Any = None) -> str:
    text = str(month or "").strip()
    if not text or text in {"本月", "这个月", "当月", "当前月"}:
        return _today_month()
    if text in {"上月", "上个月", "上个账期"}:
        return _shift_month(_today_month(), -1)
    if text in {"下月", "下个月", "下个账期"}:
        return _shift_month(_today_month(), 1)
    m = re.search(r"(20\d{2})[-年/](1[0-2]|0?[1-9])", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.search(r"(?<!\d)(1[0-2]|0?[1-9])月", text)
    if m:
        return f"{date.today().year:04d}-{int(m.group(1)):02d}"
    return text[:7] if re.match(r"^\d{4}-\d{2}", text) else _today_month()


def _normalize_date(value: Any = None) -> str:
    text = str(value or "").strip()
    if not text or text in {"今天", "今日", "当天"}:
        return date.today().isoformat()
    if text in {"昨天", "昨日"}:
        return (date.today() - timedelta(days=1)).isoformat()
    matched = re.search(r"(20\d{2})[-年/](1[0-2]|0?[1-9])[-月/](3[01]|[12]?\d)日?", text)
    if matched:
        text = f"{int(matched.group(1)):04d}-{int(matched.group(2)):02d}-{int(matched.group(3)):02d}"
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except Exception:
        return ""


def _normalize_meter_type(meter_type: Any = None) -> Optional[str]:
    text = str(meter_type or "").strip().lower()
    if not text or text in {"all", "全部", "水电", "水电表"}:
        return None
    if text in {"water", "水", "水表"}:
        return "water"
    if text in {"electric", "elec", "电", "电表"}:
        return "electric"
    return None


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status or "", status or "未知")


def _payment_total(payments: List[Dict[str, Any]]) -> float:
    return round(sum(_num(p.get("amount")) for p in payments or []), 2)


def _bill_payments(bill_id: Any) -> List[Dict[str, Any]]:
    bid = _int_or_none(bill_id)
    if not bid:
        return []
    return db.get_payments(bid) or []


def _find_active_contract(
    room_number: Any = None,
    contract_id: Any = None,
    building_id: Any = None,
    tenant_name: Any = None,
) -> Optional[Dict[str, Any]]:
    cid = _int_or_none(contract_id)
    if cid:
        contract = db.get_contract(cid)
        if contract and contract.get("status") == "active":
            return contract
        return None

    room_text = str(room_number or "").strip()
    tenant_text = str(tenant_name or "").strip()
    contracts = db.get_contracts(True, _int_or_none(building_id)) or []
    if not room_text and not tenant_text:
        return contracts[0] if len(contracts) == 1 else None

    if tenant_text:
        exact_tenant = [c for c in contracts if str(c.get("tenant_name", "")).strip() == tenant_text]
        if exact_tenant:
            return exact_tenant[0]

    exact = [c for c in contracts if str(c.get("room_number", "")).strip() == room_text]
    if exact:
        return exact[0]

    fuzzy = []
    for contract in contracts:
        haystack = "{} {} {}".format(
            contract.get("building_name", ""),
            contract.get("room_number", ""),
            contract.get("tenant_name", ""),
        )
        if room_text and room_text in haystack:
            fuzzy.append(contract)
        elif tenant_text and tenant_text in haystack:
            fuzzy.append(contract)
    return fuzzy[0] if fuzzy else None


def _resolve_active_contract(
    contract_id: Any = None,
    room_number: Any = None,
    tenant_name: Any = None,
    building_id: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    cid = _int_or_none(contract_id)
    if cid:
        contract = db.get_contract(cid)
        if not contract:
            return None, "未找到该合同"
        if contract.get("status") != "active":
            return None, "该合同不是有效合同"
        return contract, ""

    room_text = str(room_number or "").strip()
    tenant_text = str(tenant_name or "").strip()
    if not room_text and not tenant_text:
        return None, "请提供合同 ID，或说明楼栋、房间号、租户姓名"

    contracts = db.get_contracts(True, _int_or_none(building_id)) or []
    matches = contracts
    if room_text:
        matches = [item for item in matches if str(item.get("room_number") or "").strip() == room_text]
    if tenant_text:
        exact = [item for item in matches if str(item.get("tenant_name") or "").strip() == tenant_text]
        matches = exact or [item for item in matches if tenant_text in str(item.get("tenant_name") or "")]

    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        rooms = "、".join(
            "{}{}".format(str(item.get("building_name") or ""), str(item.get("room_number") or ""))
            for item in matches[:8]
        )
        return None, "匹配到多个有效合同，请补充楼栋或房间号：" + rooms
    return None, "未找到匹配的有效合同"


def _resolve_tenant_for_contract(
    tenant_id: Any = None,
    tenant_name: Any = None,
    building_id: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    tid = _int_or_none(tenant_id)
    if tid:
        tenant = db.get_tenant(tid)
        return (tenant, "") if tenant else (None, "未找到该租户")

    name = str(tenant_name or "").strip()
    if not name:
        return None, "请提供租户 ID 或租户姓名"
    tenants = db.get_tenants(True, _int_or_none(building_id)) or []
    exact = [item for item in tenants if str(item.get("name") or "").strip() == name]
    matches = exact or [item for item in tenants if name in str(item.get("name") or "")]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        names = "、".join("{}(ID {})".format(item.get("name"), item.get("id")) for item in matches[:8])
        return None, "匹配到多个租户，请补充租户 ID：" + names
    return None, "未找到该租户，请先在租户页面新增租户"


def _create_tenant_for_contract(
    tenant_name: Any = None,
    tenant_phone: Any = None,
    tenant_id_card: Any = None,
    building_id: Any = None,
    room_id: Any = None,
) -> Optional[Dict[str, Any]]:
    name = str(tenant_name or "").strip()
    if not name:
        return None
    tenant_id = db.add_tenant(
        name,
        str(tenant_phone or "").strip(),
        str(tenant_id_card or "").strip(),
        "active",
        _int_or_none(building_id),
        str(room_id) if room_id not in {None, ""} else None,
    )
    return db.get_tenant(tenant_id)


def _resolve_room_for_contract(
    room_id: Any = None,
    room_number: Any = None,
    building_id: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    rid = _int_or_none(room_id)
    if rid:
        room = db.get_room(rid)
        return (room, "") if room else (None, "未找到该房间")

    room_text = str(room_number or "").strip()
    if not room_text:
        return None, "请提供房间 ID 或房间号"
    rooms = db.get_rooms(_int_or_none(building_id)) or []
    matches = [item for item in rooms if str(item.get("room_number") or "").strip() == room_text]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        names = "、".join("{}{}".format(item.get("building_name") or "", item.get("room_number") or "") for item in matches[:8])
        return None, "多个楼栋都有该房间号，请补充楼栋：" + names
    return None, "未找到该房间"


def _resolve_building_for_contract(
    building_id: Any = None,
    building_name: Any = None,
) -> tuple[Optional[int], str, str]:
    bid = _int_or_none(building_id)
    if bid:
        building = next((item for item in (db.get_buildings() or []) if _int_or_none(item.get("id")) == bid), None)
        return (bid, str(building.get("name") or "") if building else "", "") if building else (None, "", "未找到该楼栋")

    name = str(building_name or "").strip()
    if not name:
        return None, "", ""
    buildings = db.get_buildings() or []
    exact = [item for item in buildings if str(item.get("name") or "").strip() == name]
    matches = exact or [item for item in buildings if name in str(item.get("name") or "")]
    if len(matches) == 1:
        return _int_or_none(matches[0].get("id")), str(matches[0].get("name") or ""), ""
    if len(matches) > 1:
        names = "、".join("{}(ID {})".format(item.get("name"), item.get("id")) for item in matches[:8])
        return None, name, "匹配到多个楼栋，请补充楼栋 ID：" + names
    return None, name, "未找到该楼栋"


def _validate_contract_meter(room_id: Any, meter_id: Any, meter_type: str, label: str) -> tuple[Optional[int], str]:
    mid = _int_or_none(meter_id)
    if not mid:
        return None, ""
    meter = db.get_meter(mid)
    if not meter:
        return None, label + "不存在"
    if str(meter.get("type") or "") != meter_type:
        return None, label + "类型不正确"
    if _int_or_none(meter.get("room_id")) != _int_or_none(room_id):
        return None, label + "不属于该房间"
    return mid, ""


def _contract_create_form_action(
    values: Optional[Dict[str, Any]] = None,
    missing: Optional[List[str]] = None,
    message: str = "",
) -> Dict[str, Any]:
    defaults = values or {}
    return {
        "id": "contract_create_form_" + uuid4().hex,
        "type": "create_contract",
        "title": "新建合同",
        "description": message or "请补充合同信息，提交后会生成确认卡片。",
        "submit_label": "提交表单",
        "prompt_template": (
            "请根据以下表单内容新建合同："
            "楼栋名称 {building_name}，房间号 {room_number}，租户姓名 {tenant_name}，"
            "租客手机号 {tenant_phone}，证件号 {tenant_id_card}，"
            "合同开始日期 {start_date}，合同结束日期 {end_date}，月租 {monthly_rent}，"
            "水费单价 {water_unit_price}，电费单价 {electric_unit_price}，保证金 {deposit}，"
            "其它费用 {other_fee_details}。"
        ),
        "values": defaults,
        "missing": missing or [],
        "fields": [
            {"name": "building_name", "label": "楼栋", "type": "text", "required": False, "placeholder": "例如 石潭布"},
            {"name": "room_number", "label": "房间号", "type": "text", "required": True, "placeholder": "例如 202"},
            {"name": "tenant_name", "label": "租客姓名", "type": "text", "required": True, "placeholder": "请输入租客姓名"},
            {"name": "tenant_phone", "label": "租客手机号", "type": "text", "required": False, "placeholder": "可选"},
            {"name": "tenant_id_card", "label": "证件号", "type": "text", "required": False, "placeholder": "可选"},
            {"name": "monthly_rent", "label": "月租金额", "type": "number", "required": True, "placeholder": "例如 700"},
            {"name": "start_date", "label": "合同开始日期", "type": "date", "required": True, "placeholder": "YYYY-MM-DD"},
            {"name": "end_date", "label": "合同结束日期", "type": "date", "required": False, "placeholder": "YYYY-MM-DD，可空"},
            {"name": "water_unit_price", "label": "水费单价", "type": "number", "required": False, "placeholder": "默认 0"},
            {"name": "electric_unit_price", "label": "电费单价", "type": "number", "required": False, "placeholder": "默认 0"},
            {"name": "deposit", "label": "保证金", "type": "number", "required": False, "placeholder": "默认 0"},
            {"name": "other_fee_details", "label": "其它费用", "type": "text", "required": False, "placeholder": "例如 网费50、卫生费20"},
        ],
    }


def _bill_for_contract(contract_id: Any, month: str) -> Optional[Dict[str, Any]]:
    bills = db.get_bills(month, _int_or_none(contract_id)) or []
    return bills[0] if bills else None


def _rent_plan_row(contract: Dict[str, Any], month: str) -> Dict[str, Any]:
    bill = _bill_for_contract(contract.get("id"), month)
    if not bill:
        contract_other_fees = _contract_other_fee_details(contract)
        contract_other_total = round(sum(_num(item.get("amount")) for item in contract_other_fees), 2)
        expected = round(_num(contract.get("monthly_rent")) + contract_other_total, 2)
        return {
            "building": contract.get("building_name", ""),
            "room_number": contract.get("room_number", ""),
            "tenant": contract.get("tenant_name", ""),
            "contract_id": contract.get("id"),
            "bill_id": None,
            "month": month,
            "status": "empty",
            "status_label": _status_label("empty"),
            "receivable": expected,
            "receivable_text": _money(expected),
            "paid": 0.0,
            "paid_text": _money(0),
            "due": expected,
            "due_text": _money(expected),
            "components": {
                "rent": _num(contract.get("monthly_rent")),
                "water_fee": 0.0,
                "electric_fee": 0.0,
                "other_fee": contract_other_total,
                "other_fee_details": contract_other_fees,
            },
        }

    payments = _bill_payments(bill.get("id"))
    recorded_paid = _payment_total(payments)
    status = bill.get("status") or "unpaid"
    receivable = _num(bill.get("total_amount"))
    paid_for_due = receivable if status == "paid" and recorded_paid <= 0 else recorded_paid
    due = max(receivable - paid_for_due, 0.0)
    return {
        "building": bill.get("building_name", contract.get("building_name", "")),
        "room_number": bill.get("room_number", contract.get("room_number", "")),
        "tenant": bill.get("tenant_name", contract.get("tenant_name", "")),
        "contract_id": contract.get("id"),
        "bill_id": bill.get("id"),
        "month": month,
        "status": status,
        "status_label": _status_label(status),
        "receivable": receivable,
        "receivable_text": _money(receivable),
        "paid": round(paid_for_due, 2),
        "recorded_paid": recorded_paid,
        "paid_text": _money(paid_for_due),
        "due": round(due, 2),
        "due_text": _money(due),
        "components": {
            "rent": _num(bill.get("rent_amount")),
            "water_fee": _num(bill.get("water_fee")),
            "electric_fee": _num(bill.get("electric_fee")),
            "other_fee": _num(bill.get("other_fee")),
            "other_fee_details": _normalize_other_fee_details(
                bill.get("other_fee_details"),
                bill.get("other_fee"),
            ),
        },
    }


def rent_plan_list_month_status(month: Any = None, building_id: Any = None) -> Dict[str, Any]:
    month = _normalize_month(month)
    building_id_int = _int_or_none(building_id)
    contracts = db.get_contracts(True, building_id_int) or []
    rows = [_rent_plan_row(contract, month) for contract in contracts]
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    meter_rows = _meter_rows_for_month(month, building_id_int)["rows"]
    building_name = _building_name_for_id(building_id_int)
    revenue_card = _utility_revenue_card(month, building_name, rows, meter_rows)
    return {
        "month": month,
        "total_contracts": len(contracts),
        "summary": {
            "receivable": round(sum(_num(r.get("receivable")) for r in rows), 2),
            "paid": round(sum(_num(r.get("paid")) for r in rows), 2),
            "due": round(sum(_num(r.get("due")) for r in rows), 2),
            "status_counts": counts,
            "status_labels": {k: _status_label(k) for k in counts},
        },
        "rows": rows,
        "analysis_cards": [revenue_card],
        "dashboard_html": revenue_card["html"],
    }


def rent_plan_list_uncreated_bills(month: Any = None, building_id: Any = None) -> Dict[str, Any]:
    data = rent_plan_list_month_status(month, building_id)
    rows = [row for row in data["rows"] if row["status"] == "empty"]
    return {"month": data["month"], "count": len(rows), "rows": rows}


def rent_plan_get_room_progress(
    room_number: Any,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    month = _normalize_month(month)
    contract = _find_active_contract(room_number=room_number, building_id=building_id)
    if not contract:
        return {"found": False, "message": "未找到该房间的有效合同", "month": month}
    row = _rent_plan_row(contract, month)
    explanation = (
        f"{row['building']}/{row['room_number']} {row['tenant']} 在 {month} 的状态是"
        f"{row['status_label']}，应收 {row['receivable_text']}，已收 {row['paid_text']}，"
        f"待收 {row['due_text']}。"
    )
    return {"found": True, "month": month, "progress": row, "explanation": explanation}


def rent_plan_check_anomalies(month: Any = None, building_id: Any = None) -> Dict[str, Any]:
    data = rent_plan_list_month_status(month, building_id)
    issues = []
    for row in data["rows"]:
        if row["status"] == "empty":
            issues.append({"level": "warning", "type": "missing_bill", "message": "有效合同缺少本月账单", "row": row})
        if row["bill_id"] and _num(row["receivable"]) <= 0:
            issues.append({"level": "warning", "type": "zero_amount", "message": "账单应收金额为 0 或负数", "row": row})
        if row.get("recorded_paid", row["paid"]) > row["receivable"] + 0.01:
            issues.append({"level": "warning", "type": "overpaid", "message": "实收金额大于应收金额", "row": row})
        if row["status"] == "paid" and _num(row.get("recorded_paid")) <= 0:
            issues.append({"level": "info", "type": "paid_without_payment_record", "message": "账单标记已收，但没有收款记录", "row": row})
        if row["status"] in {"unpaid", "pending_payment"} and _num(row.get("recorded_paid")) >= _num(row["receivable"]) > 0:
            issues.append({"level": "warning", "type": "status_mismatch", "message": "收款已覆盖应收，但账单状态仍待收", "row": row})
    return {"month": data["month"], "issue_count": len(issues), "issues": issues}


def _meter_types(meter_type: Any = None) -> List[str]:
    normalized = _normalize_meter_type(meter_type)
    return [normalized] if normalized else ["water", "electric"]


def meter_reading_list_month_status(
    meter_type: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    data = _meter_rows_for_month(month, building_id, meter_type)
    result = []
    for section in data["sections"]:
        normalized_rows = []
        for row in section.get("rows") or []:
            normalized_rows.append({
                "meter_id": row.get("meter_id"),
                "meter_type": row.get("meter_type"),
                "meter_type_label": row.get("meter_type_label"),
                "building": row.get("building", ""),
                "room_number": row.get("room_number", ""),
                "meter_no": row.get("meter_no", ""),
                "tenant_name": row.get("tenant_name", ""),
                "contract_id": row.get("contract_id"),
                "month": data["month"],
                "status": row.get("status"),
                "status_label": row.get("status_label"),
                "reading": row.get("reading"),
                "previous_reading": row.get("previous_reading"),
                "usage": row.get("usage"),
                "has_photo": bool(row.get("photo")),
                "photo": row.get("photo") or "",
                "remark": row.get("remark", ""),
                "cost_price": row.get("cost_price"),
                "cost_amount": row.get("cost_amount"),
            })
        result.append({
            "meter_type": section.get("meter_type"),
            "meter_type_label": section.get("meter_type_label"),
            "total": len(normalized_rows),
            "recorded": section.get("recorded", 0),
            "missing": section.get("missing", 0),
            "rows": normalized_rows,
        })
    building_name = _building_name_for_id(building_id)
    analysis_cards = []
    if data["photo_items"]:
        analysis_cards.append(_meter_photo_gallery_card(data["month"], data["photo_items"]))
    analysis_cards.append({
        "id": f"meter_analysis_{data['month']}",
        "type": "html",
        "title": f"{data['month']} 水电分析看板",
        "description": "查看本月录入、照片覆盖和用量变化。",
        "html": _meter_dashboard_html(data["month"], building_name, data["sections"]),
    })
    return {
        "month": data["month"],
        "items": result,
        "analysis_cards": analysis_cards,
        "dashboard_html": _meter_dashboard_html(data["month"], building_name, data["sections"]),
    }


def meter_reading_get_room_reading(
    room_number: Any,
    meter_type: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    data = meter_reading_list_month_status(meter_type, month, building_id)
    room_text = str(room_number or "").strip()
    matches = []
    for item in data["items"]:
        matches.extend([row for row in item["rows"] if str(row.get("room_number", "")).strip() == room_text])
    if not matches:
        for item in data["items"]:
            matches.extend([row for row in item["rows"] if room_text and room_text in str(row.get("room_number", ""))])
    photo_items = []
    for row in matches:
        photo = row.get("photo")
        if not photo:
            continue
        photo_items.append({
            "id": f"{row.get('meter_type') or ''}-{row.get('meter_id') or ''}-{row.get('room_number') or ''}",
            "photo": photo,
            "title": "{} · {}".format(row.get("meter_type_label") or "", row.get("room_number") or "").strip(" ·"),
            "room_number": row.get("room_number") or "",
            "tenant_name": row.get("tenant_name") or "",
            "meter_no": row.get("meter_no") or "",
            "reading": row.get("reading"),
            "previous_reading": row.get("previous_reading"),
            "usage": row.get("usage"),
            "month": data["month"],
        })
    analysis_cards = []
    if photo_items:
        meter_label = str(meter_type or "").strip()
        meter_title = "水电表照片" if not meter_label else ("水表照片" if meter_label == "water" else "电表照片")
        analysis_cards.append({
            "id": f"room_meter_photos_{data['month']}_{room_text}",
            "type": "photo_gallery",
            "title": f"{room_text} {data['month']} {meter_title}",
            "description": "如果这户本月有照片，会在这里直接展示。",
            "items": photo_items,
        })
    return {"month": data["month"], "found": bool(matches), "rows": matches, "analysis_cards": analysis_cards}


def meter_reading_list_missing(
    meter_type: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    data = meter_reading_list_month_status(meter_type, month, building_id)
    rows = []
    for item in data["items"]:
        rows.extend([row for row in item["rows"] if row["status"] == "missing"])
    return {"month": data["month"], "count": len(rows), "rows": rows}


def meter_reading_check_anomalies(
    meter_type: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    data = meter_reading_list_month_status(meter_type, month, building_id)
    issues = []
    for item in data["items"]:
        for row in item["rows"]:
            reading = row.get("reading")
            previous = row.get("previous_reading")
            if reading is not None and previous is not None and _num(reading) < _num(previous):
                issues.append({
                    "level": "warning",
                    "type": "reading_less_than_previous",
                    "message": "本月读数小于上月读数",
                    "row": row,
                })
    return {"month": data["month"], "issue_count": len(issues), "issues": issues}


def _escape_html(value: Any) -> str:
    return html_lib.escape(str(value or ""), quote=True)


def _active_contracts_by_room(building_id: Any = None) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for contract in db.get_contracts(True, _int_or_none(building_id)) or []:
        room_number = str(contract.get("room_number") or "").strip()
        if room_number and room_number not in mapping:
            mapping[room_number] = contract
    return mapping


def _building_name_for_id(building_id: Any = None) -> str:
    bid = _int_or_none(building_id)
    if not bid:
        return ""
    for building in db.get_buildings() or []:
        if _int_or_none(building.get("id")) == bid:
            return str(building.get("name") or "")
    return ""


def _meter_rows_for_month(month: Any, building_id: Any = None, meter_type: Any = None) -> Dict[str, Any]:
    target_month = _normalize_month(month)
    contracts_by_room = _active_contracts_by_room(building_id)
    meter_types = _meter_types(meter_type)
    sections: List[Dict[str, Any]] = []
    all_rows: List[Dict[str, Any]] = []
    photo_items: List[Dict[str, Any]] = []
    issue_rows: List[Dict[str, Any]] = []
    for mtype in meter_types:
        rows = db.get_monthly_meter_readings(mtype, _int_or_none(building_id), target_month) or []
        items: List[Dict[str, Any]] = []
        for row in rows:
            room_number = str(row.get("room_number") or "").strip()
            contract = contracts_by_room.get(room_number) or {}
            item = dict(row)
            item["meter_id"] = item.get("id")
            item["meter_type"] = mtype
            item["meter_type_label"] = METER_TYPE_LABELS.get(mtype, mtype)
            item["building"] = item.get("building_name", "")
            item["tenant_name"] = contract.get("tenant_name", "")
            item["contract_id"] = contract.get("id")
            item["water_unit_price"] = _num(contract.get("water_unit_price"))
            item["electric_unit_price"] = _num(contract.get("electric_unit_price"))
            raw_usage = item.get("usage")
            item["usage"] = raw_usage
            item["reading"] = item.get("reading")
            item["previous_reading"] = item.get("previous_reading")
            item["has_photo"] = bool(item.get("photo"))
            item["cost_price"] = WATER_COST_PRICE if mtype == "water" else ELECTRIC_COST_PRICE
            item["cost_amount"] = round(_num(raw_usage) * item["cost_price"], 2) if raw_usage is not None else 0.0
            items.append(item)
            all_rows.append(item)
            if item.get("photo"):
                photo_items.append({
                    "id": f"{mtype}-{item.get('meter_id')}-{room_number}",
                    "photo": item.get("photo"),
                    "title": "{} · {}".format(item.get("meter_type_label") or "", room_number).strip(" ·"),
                    "room_number": room_number,
                    "tenant_name": item.get("tenant_name") or "",
                    "meter_no": item.get("meter_no") or "",
                    "reading": item.get("reading"),
                    "previous_reading": item.get("previous_reading"),
                    "usage": item.get("usage"),
                    "month": target_month,
                })
        sections.append({
            "meter_type": mtype,
            "meter_type_label": METER_TYPE_LABELS.get(mtype, mtype),
            "rows": items,
            "recorded": sum(1 for item in items if item.get("status") == "recorded"),
            "missing": sum(1 for item in items if item.get("status") == "missing"),
            "photo_count": sum(1 for item in items if item.get("photo")),
            "usage_total": round(sum(_num(item.get("usage")) for item in items if item.get("usage") is not None), 2),
            "cost_total": round(sum(_num(item.get("cost_amount")) for item in items), 2),
        })
        issue_rows.extend([item for item in items if item.get("usage") is not None and item.get("previous_reading") is not None and _num(item.get("reading")) < _num(item.get("previous_reading"))])
    return {
        "month": target_month,
        "building_id": _int_or_none(building_id),
        "sections": sections,
        "rows": all_rows,
        "photo_items": photo_items,
        "issue_rows": issue_rows,
    }


def _meter_photo_gallery_card(month: str, photo_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": f"meter_photo_gallery_{month}",
        "type": "photo_gallery",
        "title": f"{month} 月度表具照片",
        "description": "有照片的水表或电表读数会集中展示在这里。",
        "items": photo_items[:12],
    }


def _meter_dashboard_html(month: str, building_name: str, sections: List[Dict[str, Any]]) -> str:
    total_recorded = sum(_num(section.get("recorded")) for section in sections)
    total_missing = sum(_num(section.get("missing")) for section in sections)
    total_photo = sum(_num(section.get("photo_count")) for section in sections)
    total_usage = sum(_num(section.get("usage_total")) for section in sections)
    total_cost = sum(_num(section.get("cost_total")) for section in sections)
    top_rows = sorted(
        [row for section in sections for row in (section.get("rows") or []) if isinstance(row, dict)],
        key=lambda item: (_num(item.get("usage")), _num(item.get("cost_amount"))),
        reverse=True,
    )[:8]

    def stat_card(label: str, value: str, hint: str = "") -> str:
        return (
            '<div class="dash-stat"><span>{label}</span><strong>{value}</strong>{hint}</div>'
            .format(label=_escape_html(label), value=_escape_html(value), hint=(f'<em>{_escape_html(hint)}</em>' if hint else ""))
        )

    section_html = []
    for section in sections:
        rows = section.get("rows") or []
        bar_total = max(sum(_num(item.get("usage")) for item in rows if item.get("usage") is not None), 1)
        row_html = []
        for row in sorted(rows, key=lambda item: (_num(item.get("usage")), _num(item.get("cost_amount"))), reverse=True)[:8]:
            usage = _num(row.get("usage"))
            bar_width = min(100, round(usage / bar_total * 100)) if bar_total else 0
            row_html.append(
                "<tr>"
                f"<td><b>{_escape_html(row.get('room_number'))}</b><div class='dash-sub'>{_escape_html(row.get('tenant_name') or '无租客')}</div></td>"
                f"<td>{_escape_html(row.get('meter_no') or '')}</td>"
                f"<td>{_escape_html(row.get('previous_reading') or '')}</td>"
                f"<td><b>{_escape_html(row.get('reading') or '')}</b></td>"
                f"<td>{_escape_html(usage if row.get('usage') is not None else '')}<div class='dash-bar'><i style='width:{bar_width}%'></i></div></td>"
                f"<td>{_escape_html(_money(row.get('cost_amount')))}</td>"
                f"<td>{'有照片' if row.get('photo') else '无'}</td>"
                "</tr>"
            )
        section_html.append(
            f"""
            <section class="dash-section">
              <div class="dash-section-head">
                <h3>{_escape_html(section.get('meter_type_label') or '')}</h3>
                <span>{_escape_html(section.get('recorded') or 0)} 已录入 / {_escape_html(section.get('missing') or 0)} 未录入</span>
              </div>
              <table>
                <thead><tr><th>房间</th><th>表号</th><th>上月</th><th>本月</th><th>用量</th><th>成本</th><th>照片</th></tr></thead>
                <tbody>{''.join(row_html) or '<tr><td colspan="7">暂无数据</td></tr>'}</tbody>
              </table>
            </section>
            """
        )

    table_rows = []
    for row in top_rows:
        table_rows.append(
            "<tr>"
            f"<td>{_escape_html(row.get('meter_type_label') or '')}</td>"
            f"<td><b>{_escape_html(row.get('room_number'))}</b></td>"
            f"<td>{_escape_html(row.get('tenant_name') or '无租客')}</td>"
            f"<td>{_escape_html(row.get('previous_reading') or '')}</td>"
            f"<td><b>{_escape_html(row.get('reading') or '')}</b></td>"
            f"<td>{_escape_html(row.get('usage') or '')}</td>"
            f"<td>{_escape_html(_money(row.get('cost_amount')))}</td>"
            "</tr>"
        )

    return f"""
    <div class="meter-dashboard">
      <style>
        .meter-dashboard{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#F8FBFF;color:#0F172A;padding:16px;box-sizing:border-box}}
        .meter-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}}
        .meter-head h2{{margin:0;font-size:18px;line-height:1.3}}
        .meter-head p{{margin:6px 0 0;color:#64748B;font-size:12px;line-height:1.5}}
        .meter-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}}
        .dash-stat{{background:#fff;border:1px solid #DBEAFE;border-radius:8px;padding:12px 12px 10px;box-shadow:0 2px 8px rgba(15,23,42,.04)}}
        .dash-stat span{{display:block;font-size:11px;color:#64748B}}
        .dash-stat strong{{display:block;margin-top:6px;font-size:22px;line-height:1.2;color:#0F172A}}
        .dash-stat em{{display:block;margin-top:4px;font-style:normal;font-size:11px;color:#94A3B8}}
        .dash-section{{margin-top:14px;background:#fff;border:1px solid #E2E8F0;border-radius:8px;overflow:hidden}}
        .dash-section-head{{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:12px 14px;border-bottom:1px solid #E2E8F0;background:#F8FAFC}}
        .dash-section-head h3{{margin:0;font-size:14px;color:#0F172A}}
        .dash-section-head span{{font-size:12px;color:#64748B}}
        .dash-section table{{width:100%;border-collapse:collapse;font-size:12px}}
        .dash-section th,.dash-section td{{padding:9px 10px;border-bottom:1px solid #E2E8F0;text-align:left;vertical-align:top}}
        .dash-section th{{font-weight:600;color:#475569;background:#FBFDFF}}
        .dash-section td b{{color:#0F172A}}
        .dash-sub{{margin-top:2px;font-size:11px;color:#94A3B8}}
        .dash-bar{{width:100%;height:6px;margin-top:6px;background:#E2E8F0;border-radius:999px;overflow:hidden}}
        .dash-bar i{{display:block;height:100%;background:linear-gradient(90deg,#3B82F6,#14B8A6);border-radius:999px}}
        .meter-grid-top{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}
        .meter-note{{margin-top:10px;font-size:11px;color:#64748B}}
        @media (max-width:860px){{.meter-grid,.meter-grid-top{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
      </style>
      <div class="meter-head">
        <div>
          <h2>{_escape_html(building_name or "全部楼栋")} · {month} 水电分析看板</h2>
          <p>聚焦本月表具录入、照片覆盖、异常读数和用量变化，方便快速看出哪几户波动明显。</p>
        </div>
      </div>
      <div class="meter-grid-top">
        {stat_card("已录入表具", f"{int(total_recorded)} 个", "本月有读数的表具")}
        {stat_card("未录入表具", f"{int(total_missing)} 个", "还需要补录")}
        {stat_card("带照片表具", f"{int(total_photo)} 个", "图片更容易回看")}
        {stat_card("总用量 / 成本", f"{_money(total_usage)} / {_money(total_cost)}", "按固定成本口径")}
      </div>
      {''.join(section_html) or '<div class="dash-section"><div class="dash-section-head"><h3>水电表</h3><span>暂无数据</span></div></div>'}
      <section class="dash-section">
        <div class="dash-section-head">
          <h3>本月用量变化较大</h3>
          <span>优先关注这些房间</span>
        </div>
        <table>
          <thead><tr><th>类型</th><th>房间</th><th>租客</th><th>上月</th><th>本月</th><th>用量</th><th>成本</th></tr></thead>
          <tbody>{''.join(table_rows) or '<tr><td colspan="7">暂无数据</td></tr>'}</tbody>
        </table>
      </section>
      <div class="meter-note">成本口径：水 2.1，电 0.6。</div>
    </div>
    """


def _utility_revenue_html(month: str, building_name: str, plan_rows: List[Dict[str, Any]], meter_rows: List[Dict[str, Any]]) -> str:
    meter_by_room: Dict[tuple[str, str], Dict[str, Any]] = {}
    for row in meter_rows:
        room_number = str(row.get("room_number") or "").strip()
        mtype = str(row.get("meter_type") or "").strip()
        if room_number and mtype:
            meter_by_room[(room_number, mtype)] = row

    total_receivable = 0.0
    total_paid = 0.0
    total_cost = 0.0
    rooms: List[Dict[str, Any]] = []
    for row in plan_rows:
        if not isinstance(row, dict):
            continue
        utility_amount = round(_num(row.get("components", {}).get("water_fee")) + _num(row.get("components", {}).get("electric_fee")), 2)
        bill_total = _num(row.get("receivable"))
        paid_for_bill = _num(row.get("paid"))
        utility_ratio = utility_amount / bill_total if bill_total > 0 else 0
        utility_paid = min(utility_amount, paid_for_bill * utility_ratio) if utility_amount > 0 else 0.0
        water_row = meter_by_room.get((str(row.get("room_number") or "").strip(), "water"))
        electric_row = meter_by_room.get((str(row.get("room_number") or "").strip(), "electric"))
        water_usage = _num((water_row or {}).get("usage"))
        electric_usage = _num((electric_row or {}).get("usage"))
        cost = round(
            water_usage * WATER_COST_PRICE + electric_usage * ELECTRIC_COST_PRICE,
            2,
        )
        profit = round(utility_paid - cost, 2)
        rooms.append({
            "room_number": row.get("room_number"),
            "tenant": row.get("tenant"),
            "utility_amount": utility_amount,
            "utility_paid": utility_paid,
            "cost": cost,
            "profit": profit,
            "water_usage": water_usage,
            "electric_usage": electric_usage,
        })
        total_receivable += utility_amount
        total_paid += utility_paid
        total_cost += cost

    profit_total = round(total_paid - total_cost, 2)
    top_rooms = sorted(rooms, key=lambda item: abs(_num(item.get("profit"))), reverse=True)[:8]
    rows_html = []
    for row in top_rooms:
        rows_html.append(
            "<tr>"
            f"<td><b>{_escape_html(row.get('room_number'))}</b></td>"
            f"<td>{_escape_html(row.get('tenant') or '无租客')}</td>"
            f"<td>{_escape_html(_money(row.get('utility_amount')))}</td>"
            f"<td>{_escape_html(_money(row.get('utility_paid')))}</td>"
            f"<td>{_escape_html(_money(row.get('cost')))}</td>"
            f"<td><b>{_escape_html(_money(row.get('profit')))}</b></td>"
            "</tr>"
        )
    return f"""
    <div class="meter-dashboard">
      <style>
        .meter-dashboard{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#F8FBFF;color:#0F172A;padding:16px;box-sizing:border-box}}
        .meter-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}}
        .meter-head h2{{margin:0;font-size:18px;line-height:1.3}}
        .meter-head p{{margin:6px 0 0;color:#64748B;font-size:12px;line-height:1.5}}
        .meter-grid-top{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}}
        .dash-stat{{background:#fff;border:1px solid #DBEAFE;border-radius:8px;padding:12px 12px 10px;box-shadow:0 2px 8px rgba(15,23,42,.04)}}
        .dash-stat span{{display:block;font-size:11px;color:#64748B}}
        .dash-stat strong{{display:block;margin-top:6px;font-size:22px;line-height:1.2;color:#0F172A}}
        .dash-stat em{{display:block;margin-top:4px;font-style:normal;font-size:11px;color:#94A3B8}}
        .dash-section{{margin-top:14px;background:#fff;border:1px solid #E2E8F0;border-radius:8px;overflow:hidden}}
        .dash-section-head{{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:12px 14px;border-bottom:1px solid #E2E8F0;background:#F8FAFC}}
        .dash-section-head h3{{margin:0;font-size:14px;color:#0F172A}}
        .dash-section-head span{{font-size:12px;color:#64748B}}
        .dash-section table{{width:100%;border-collapse:collapse;font-size:12px}}
        .dash-section th,.dash-section td{{padding:9px 10px;border-bottom:1px solid #E2E8F0;text-align:left;vertical-align:top}}
        .dash-section th{{font-weight:600;color:#475569;background:#FBFDFF}}
        .dash-note{{margin-top:10px;font-size:11px;color:#64748B}}
        @media (max-width:860px){{.meter-grid-top{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
      </style>
      <div class="meter-head">
        <div>
          <h2>{_escape_html(building_name or "全部楼栋")} · {month} 收益看板</h2>
          <p>这里按水 2.1、电 0.6 的成本口径，快速看每户水电收入、实收、成本和利润。</p>
        </div>
      </div>
      <div class="meter-grid-top">
        <div class="dash-stat"><span>水电应收</span><strong>{_escape_html(_money(total_receivable))}</strong><em>账单里水费+电费总和</em></div>
        <div class="dash-stat"><span>水电实收</span><strong>{_escape_html(_money(total_paid))}</strong><em>按收款比例估算</em></div>
        <div class="dash-stat"><span>水电成本</span><strong>{_escape_html(_money(total_cost))}</strong><em>按实际用量计算</em></div>
        <div class="dash-stat"><span>水电收益</span><strong>{_escape_html(_money(profit_total))}</strong><em>实收减成本</em></div>
      </div>
      <section class="dash-section">
        <div class="dash-section-head">
          <h3>本月收益变化较大房间</h3>
          <span>优先看这些户</span>
        </div>
        <table>
          <thead><tr><th>房间</th><th>租客</th><th>应收</th><th>实收</th><th>成本</th><th>收益</th></tr></thead>
          <tbody>{''.join(rows_html) or '<tr><td colspan="6">暂无数据</td></tr>'}</tbody>
        </table>
      </section>
      <div class="dash-note">收益看板会随着账单实收和表具用量变化一起更新。</div>
    </div>
    """


def _utility_revenue_card(month: str, building_name: str, plan_rows: List[Dict[str, Any]], meter_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": f"utility_revenue_{month}",
        "type": "html",
        "title": f"{month} 收益看板",
        "description": "按水 2.1、电 0.6 的成本口径计算本月水电收益。",
        "html": _utility_revenue_html(month, building_name, plan_rows, meter_rows),
    }


def _clean_room_text(room_number: Any) -> str:
    return str(room_number or "").strip().replace("房间", "").replace("房", "")


def _find_meter_row_for_room(
    room_number: Any,
    meter_type: str,
    month: str,
    building_id: Any = None,
) -> Optional[Dict[str, Any]]:
    room_text = _clean_room_text(room_number)
    rows = db.get_monthly_meter_readings(meter_type, _int_or_none(building_id), month) or []
    exact = [row for row in rows if _clean_room_text(row.get("room_number")) == room_text]
    if exact:
        return exact[0]
    fuzzy = [row for row in rows if room_text and room_text in _clean_room_text(row.get("room_number"))]
    return fuzzy[0] if fuzzy else None


def _public_meter_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    photo = item.pop("photo", "")
    item["has_photo"] = bool(photo)
    return item


def meter_reading_save_from_ai(
    room_number: Any,
    meter_type: Any,
    month: Any,
    reading: Any,
    photo: Any = "",
    building_id: Any = None,
    overwrite: Any = False,
    remark: Any = "AI助手录入",
) -> Dict[str, Any]:
    month = _normalize_month(month)
    mtype = _normalize_meter_type(meter_type)
    if mtype not in {"water", "electric"}:
        return {"success": False, "message": "请说明要录入水表还是电表"}

    value = _float_or_none(reading)
    if value is None:
        return {"success": False, "message": "未获取到有效读数"}

    row = _find_meter_row_for_room(room_number, mtype, month, building_id)
    if not row:
        return {"success": False, "message": "未找到该房间对应的表具", "month": month, "meter_type": mtype}

    action_args = {
        "meter_id": row.get("id"),
        "building_id": row.get("building_id"),
        "room_number": row.get("room_number"),
        "meter_type": mtype,
        "month": month,
        "reading": value,
        "photo": str(photo or ""),
        "remark": str(remark or "AI助手录入"),
    }
    action_verb = "更新" if row.get("reading_id") else "录入"
    action = _pending_action(
        "save_meter_reading",
        f"{action_verb}{row.get('room_number')} {month} {METER_TYPE_LABELS.get(mtype, mtype)}读数 {value}",
        "confirm_save_meter_reading",
        action_args,
        {
            "building_name": row.get("building_name"),
            "room_number": row.get("room_number"),
            "meter_type": mtype,
            "meter_type_label": METER_TYPE_LABELS.get(mtype, mtype),
            "month": month,
            "reading": value,
            "previous_reading": row.get("previous_reading"),
            "usage": round(max(0, value - _num(row.get("previous_reading"))), 2),
            "photo_saved": bool(photo),
            "will_overwrite": bool(row.get("reading_id")),
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "meter_reading_prepared",
        "month": month,
        "meter_type": mtype,
        "meter_type_label": METER_TYPE_LABELS.get(mtype, mtype),
        "room_number": row.get("room_number"),
        "meter_id": row.get("id"),
        "reading": value,
        "photo_saved": bool(photo),
        "pending_action": action,
        "message": "已识别读数并准备录入，请用户确认后再写入。",
    }


def confirm_save_meter_reading(
    meter_id: Any,
    month: Any,
    reading: Any,
    photo: Any = "",
    remark: Any = "AI助手确认录入",
    building_id: Any = None,
    room_number: Any = "",
    meter_type: Any = "",
) -> Dict[str, Any]:
    month = _normalize_month(month)
    value = _float_or_none(reading)
    mid = _int_or_none(meter_id)
    if not mid or value is None:
        return {"success": False, "message": "确认参数缺少表具 ID 或读数"}
    saved = db.save_monthly_meter_reading(mid, month, value, str(photo or ""), str(remark or "AI助手确认录入"))
    latest = None
    if room_number and meter_type:
        latest = _find_meter_row_for_room(room_number, str(meter_type), month, building_id)
    bill_photo_synced = False
    synced_bill_id = None
    if photo and room_number:
        contract = _find_active_contract(room_number=room_number, building_id=building_id)
        bill = _bill_for_contract(contract.get("id"), month) if contract else None
        if bill:
            if _normalize_meter_type(meter_type) == "water":
                db.update_bill(bill.get("id"), water_photo=str(photo))
            elif _normalize_meter_type(meter_type) == "electric":
                db.update_bill(bill.get("id"), electric_photo=str(photo))
            bill_photo_synced = True
            synced_bill_id = bill.get("id")
    return {
        "success": True,
        "action": "meter_reading_saved",
        "month": month,
        "meter_id": mid,
        "room_number": room_number,
        "meter_type": meter_type,
        "reading": value,
        "photo_saved": bool(photo),
        "bill_photo_synced": bill_photo_synced,
        "synced_bill_id": synced_bill_id,
        "result": saved,
        "row": _public_meter_row(latest) if latest else None,
    }


def _reading_for_contract(contract: Dict[str, Any], meter_type: str, month: str) -> Optional[Dict[str, Any]]:
    room = db.get_room(contract.get("room_id")) or {}
    rows = db.get_monthly_meter_readings(meter_type, room.get("building_id"), month) or []
    bound_id = contract.get("water_meter_id") if meter_type == "water" else contract.get("electric_meter_id")
    room_rows = [row for row in rows if row.get("room_id") == contract.get("room_id")]
    if bound_id:
        for row in room_rows:
            if _int_or_none(row.get("id")) == _int_or_none(bound_id):
                return row
    return room_rows[0] if room_rows else None


def _bill_detail_payload(bill: Dict[str, Any]) -> Dict[str, Any]:
    payments = _bill_payments(bill.get("id"))
    paid = _payment_total(payments)
    receivable = _num(bill.get("total_amount"))
    return {
        "bill": bill,
        "components": {
            "rent": _num(bill.get("rent_amount")),
            "water_fee": _num(bill.get("water_fee")),
            "electric_fee": _num(bill.get("electric_fee")),
            "other_fee": _num(bill.get("other_fee")),
            "other_fee_details": _normalize_other_fee_details(
                bill.get("other_fee_details"),
                bill.get("other_fee"),
            ),
            "total": receivable,
        },
        "payments": payments,
        "payment_summary": {
            "receivable": receivable,
            "paid": paid,
            "due": round(max(receivable - paid, 0), 2),
            "difference": round(receivable - paid, 2),
        },
    }


def bill_explain_amount(bill_id: Any) -> Dict[str, Any]:
    bill = db.get_bill(_int_or_none(bill_id))
    if not bill:
        return {"found": False, "message": "未找到账单"}
    payload = _bill_detail_payload(bill)
    c = payload["components"]
    calculated = round(c["rent"] + c["water_fee"] + c["electric_fee"] + c["other_fee"], 2)
    payload["calculation"] = (
        f"{_money(c['rent'])} 房租 + {_money(c['water_fee'])} 水费 + "
        f"{_money(c['electric_fee'])} 电费 + {_money(c['other_fee'])} 其他费用 = {_money(calculated)}"
    )
    payload["matches_total"] = abs(calculated - c["total"]) <= 0.01
    payload["found"] = True
    return payload


def bill_get_bill_detail(
    bill_id: Any = None,
    room_number: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    if bill_id:
        bill = db.get_bill(_int_or_none(bill_id))
        return {"found": bool(bill), **(_bill_detail_payload(bill) if bill else {"message": "未找到账单"})}

    month = _normalize_month(month)
    contract = _find_active_contract(room_number=room_number, building_id=building_id)
    if not contract:
        return {"found": False, "month": month, "message": "未找到该房间的有效合同"}
    bill = _bill_for_contract(contract.get("id"), month)
    if not bill:
        return {"found": False, "month": month, "contract": contract, "message": "该月份尚未生成账单"}
    return {"found": True, "month": month, **_bill_detail_payload(bill)}


def bill_generate_draft(
    contract_id: Any = None,
    room_number: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    month = _normalize_month(month)
    contract = _find_active_contract(room_number=room_number, contract_id=contract_id, building_id=building_id)
    if not contract:
        return {"success": False, "month": month, "message": "未找到有效合同，无法生成草稿"}

    water = _reading_for_contract(contract, "water", month)
    electric = _reading_for_contract(contract, "electric", month)
    missing = []

    water_usage = water.get("usage") if water else None
    electric_usage = electric.get("usage") if electric else None
    if water_usage is None:
        missing.append("水表本月读数")
    if electric_usage is None:
        missing.append("电表本月读数")

    rent = _num(contract.get("monthly_rent"))
    water_fee = round(_num(water_usage) * _num(contract.get("water_unit_price")), 2) if water_usage is not None else 0.0
    electric_fee = round(_num(electric_usage) * _num(contract.get("electric_unit_price")), 2) if electric_usage is not None else 0.0
    other_fee_details = _contract_other_fee_details(contract)
    other_fee = round(sum(_num(item.get("amount")) for item in other_fee_details), 2)
    total = round(rent + water_fee + electric_fee + other_fee, 2)

    return {
        "success": True,
        "draft_only": True,
        "saved": False,
        "month": month,
        "contract": contract,
        "draft": {
            "contract_id": contract.get("id"),
            "billing_month": month,
            "rent_amount": rent,
            "water_last": water.get("previous_reading") if water else None,
            "water_curr": water.get("reading") if water else None,
            "water_usage": water_usage,
            "water_fee": water_fee,
            "water_photo": water.get("photo", "") if water else "",
            "electric_last": electric.get("previous_reading") if electric else None,
            "electric_curr": electric.get("reading") if electric else None,
            "electric_usage": electric_usage,
            "electric_fee": electric_fee,
            "electric_photo": electric.get("photo", "") if electric else "",
            "other_fee": other_fee,
            "other_fee_details": other_fee_details,
            "total_amount": total,
        },
        "missing": missing,
    }


def bill_validate_preview(
    bill_id: Any = None,
    contract_id: Any = None,
    room_number: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    issues = []
    if bill_id:
        detail = bill_get_bill_detail(bill_id=bill_id)
        if not detail.get("found"):
            return detail
        bill = detail["bill"]
        components = detail["components"]
        calculated = round(components["rent"] + components["water_fee"] + components["electric_fee"] + components["other_fee"], 2)
        if abs(calculated - components["total"]) > 0.01:
            issues.append({"level": "warning", "message": "账单总金额和分项合计不一致"})
        if _num(bill.get("water_current_reading")) < _num(bill.get("water_last_reading")):
            issues.append({"level": "warning", "message": "水表本期读数小于上期读数"})
        if _num(bill.get("electric_current_reading")) < _num(bill.get("electric_last_reading")):
            issues.append({"level": "warning", "message": "电表本期读数小于上期读数"})
        return {"found": True, "source": "saved_bill", "issue_count": len(issues), "issues": issues, "detail": detail}

    draft = bill_generate_draft(contract_id=contract_id, room_number=room_number, month=month, building_id=building_id)
    if not draft.get("success"):
        return draft
    for item in draft.get("missing", []):
        issues.append({"level": "warning", "message": f"缺少{item}"})
    d = draft["draft"]
    if _num(d.get("water_curr")) < _num(d.get("water_last")):
        issues.append({"level": "warning", "message": "水表本期读数小于上期读数"})
    if _num(d.get("electric_curr")) < _num(d.get("electric_last")):
        issues.append({"level": "warning", "message": "电表本期读数小于上期读数"})
    if _num(d.get("total_amount")) <= 0:
        issues.append({"level": "warning", "message": "账单总金额为 0 或负数"})
    return {"found": True, "source": "draft", "issue_count": len(issues), "issues": issues, "draft": draft}


def _receipt_item(
    name: str,
    current: Any,
    last: Any,
    unit_price: Any,
    amount: Any,
    fraction_digits: int,
) -> Dict[str, Any]:
    has_current = current is not None and current != ""
    usage = None
    if has_current:
        usage = round(max(0, _num(current) - _num(last)), fraction_digits)
    return {
        "name": name,
        "current": current if has_current else None,
        "last": last if last is not None and last != "" else None,
        "usage": usage,
        "unit_price": _num(unit_price),
        "amount": _num(amount),
    }


def _receipt_payload_from_bill(bill: Dict[str, Any]) -> Dict[str, Any]:
    contract = db.get_contract(bill.get("contract_id")) or {}
    month = bill.get("billing_month") or _today_month()
    room_number = bill.get("room_number") or contract.get("room_number", "")
    other_fee_details = _normalize_other_fee_details(
        bill.get("other_fee_details"),
        bill.get("other_fee"),
    )
    return {
        "image_type": "bill_receipt",
        "source": "saved_bill",
        "bill_id": bill.get("id"),
        "contract_id": bill.get("contract_id"),
        "file_name": f"bill_{month}_{room_number}.png",
        "receipt": {
            "title": "房租及费用收据",
            "no": f"{str(month).replace('-', '')}{room_number}",
            "month": month,
            "room_number": room_number,
            "tenant_name": bill.get("tenant_name") or contract.get("tenant_name", ""),
            "collector": "吴钦腾",
            "issue_date": date.today().isoformat(),
            "items": [
                _receipt_item(
                    "水费（吨）",
                    bill.get("water_current_reading"),
                    bill.get("water_last_reading"),
                    contract.get("water_unit_price"),
                    bill.get("water_fee"),
                    1,
                ),
                _receipt_item(
                    "电费（度）",
                    bill.get("electric_current_reading"),
                    bill.get("electric_last_reading"),
                    contract.get("electric_unit_price"),
                    bill.get("electric_fee"),
                    0,
                ),
                {
                    "name": "房租",
                    "current": None,
                    "last": None,
                    "usage": None,
                    "unit_price": None,
                    "amount": _num(bill.get("rent_amount")),
                },
                *[
                    {
                        "name": item["name"],
                        "current": None,
                        "last": None,
                        "usage": None,
                        "unit_price": None,
                        "amount": item["amount"],
                    }
                    for item in other_fee_details
                ],
            ],
            "total_amount": _num(bill.get("total_amount")),
            "water_photo": bill.get("water_photo") or "",
            "electric_photo": bill.get("electric_photo") or "",
        },
    }


def _receipt_payload_from_draft(draft_payload: Dict[str, Any]) -> Dict[str, Any]:
    contract = draft_payload.get("contract") or {}
    draft = draft_payload.get("draft") or {}
    month = draft.get("billing_month") or draft_payload.get("month") or _today_month()
    room_number = contract.get("room_number", "")
    other_fee_details = _normalize_other_fee_details(
        draft.get("other_fee_details"),
        draft.get("other_fee"),
    )
    return {
        "image_type": "bill_receipt",
        "source": "draft",
        "bill_id": None,
        "contract_id": contract.get("id"),
        "file_name": f"bill_draft_{month}_{room_number}.png",
        "receipt": {
            "title": "房租及费用收据",
            "no": f"{str(month).replace('-', '')}{room_number}",
            "month": month,
            "room_number": room_number,
            "tenant_name": contract.get("tenant_name", ""),
            "collector": "吴钦腾",
            "issue_date": date.today().isoformat(),
            "items": [
                _receipt_item(
                    "水费（吨）",
                    draft.get("water_curr"),
                    draft.get("water_last"),
                    contract.get("water_unit_price"),
                    draft.get("water_fee"),
                    1,
                ),
                _receipt_item(
                    "电费（度）",
                    draft.get("electric_curr"),
                    draft.get("electric_last"),
                    contract.get("electric_unit_price"),
                    draft.get("electric_fee"),
                    0,
                ),
                {
                    "name": "房租",
                    "current": None,
                    "last": None,
                    "usage": None,
                    "unit_price": None,
                    "amount": _num(draft.get("rent_amount")),
                },
                *[
                    {
                        "name": item["name"],
                        "current": None,
                        "last": None,
                        "usage": None,
                        "unit_price": None,
                        "amount": item["amount"],
                    }
                    for item in other_fee_details
                ],
            ],
            "total_amount": _num(draft.get("total_amount")),
            "water_photo": draft.get("water_photo") or "",
            "electric_photo": draft.get("electric_photo") or "",
        },
    }


def bill_get_receipt_image_data(
    bill_id: Any = None,
    contract_id: Any = None,
    room_number: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    """返回 AIChat 渲染账单图片所需的结构化数据，不生成或保存账单。"""
    if bill_id:
        bill = db.get_bill(_int_or_none(bill_id))
        if not bill:
            return {"found": False, "message": "未找到账单"}
        return {"found": True, **_receipt_payload_from_bill(bill)}

    month = _normalize_month(month)
    contract = _find_active_contract(room_number=room_number, contract_id=contract_id, building_id=building_id)
    if not contract:
        return {"found": False, "month": month, "message": "未找到有效合同，无法生成账单图片"}

    bill = _bill_for_contract(contract.get("id"), month)
    if bill:
        return {"found": True, **_receipt_payload_from_bill(bill)}

    draft_payload = bill_generate_draft(contract_id=contract.get("id"), month=month)
    if not draft_payload.get("success"):
        return draft_payload
    payload = _receipt_payload_from_draft(draft_payload)
    payload["draft_only"] = True
    payload["missing"] = draft_payload.get("missing", [])
    return {"found": True, **payload}


def bill_create_from_ai(
    room_number: Any = None,
    contract_id: Any = None,
    month: Any = None,
    building_id: Any = None,
    tenant_name: Any = None,
    overwrite: Any = False,
    rent_amount: Any = None,
    water_fee: Any = None,
    electric_fee: Any = None,
    other_fee: Any = None,
    other_fee_details: Any = None,
    remove_other_fee_names: Any = None,
    clear_other_fees: Any = False,
    water_curr: Any = None,
    electric_curr: Any = None,
    water_last: Any = None,
    electric_last: Any = None,
) -> Dict[str, Any]:
    month = _normalize_month(month)
    contract = _find_active_contract(room_number=room_number, contract_id=contract_id, building_id=building_id, tenant_name=tenant_name)
    if not contract:
        return {"success": False, "month": month, "message": "未找到有效合同，无法生成账单"}

    existing = _bill_for_contract(contract.get("id"), month)
    draft_payload = bill_generate_draft(contract_id=contract.get("id"), month=month)
    if not draft_payload.get("success"):
        return draft_payload

    draft = draft_payload.get("draft") or {}
    for key, value in {
        "rent_amount": rent_amount,
        "water_fee": water_fee,
        "electric_fee": electric_fee,
        "water_curr": water_curr,
        "electric_curr": electric_curr,
        "water_last": water_last,
        "electric_last": electric_last,
    }.items():
        if value is not None and value != "":
            draft[key] = _num(value)

    remove_fee_names = _normalize_other_fee_names(remove_other_fee_names)
    clear_other_fee_requested = _is_clear_other_fee_request(remove_fee_names, clear_other_fees)
    if other_fee_details is not None:
        normalized_other_fees = _normalize_other_fee_details(other_fee_details)
    elif other_fee is not None and other_fee != "":
        normalized_other_fees = _normalize_other_fee_details([], other_fee)
    elif existing and (_bool(overwrite) or remove_fee_names or clear_other_fee_requested):
        normalized_other_fees = _normalize_other_fee_details(
            existing.get("other_fee_details"),
            existing.get("other_fee"),
        )
    else:
        normalized_other_fees = _normalize_other_fee_details(
            draft.get("other_fee_details"),
            draft.get("other_fee"),
        )
    if clear_other_fee_requested:
        normalized_other_fees = []
    elif remove_fee_names:
        before_remove = normalized_other_fees
        normalized_other_fees = [
            item for item in normalized_other_fees
            if not any(_matches_other_fee_name(item.get("name"), name) for name in remove_fee_names)
        ]
        if len(normalized_other_fees) == len(before_remove):
            existing_names = [str(item.get("name") or "") for item in before_remove if item.get("name")]
            return {
                "success": False,
                "message": "未在其它费用中找到要删除的项目，请确认项目名称。",
                "remove_other_fee_names": remove_fee_names,
                "existing_other_fee_names": existing_names,
                "existing_other_fee_details": before_remove,
            }
    draft["other_fee_details"] = normalized_other_fees
    draft["other_fee"] = round(sum(_num(item.get("amount")) for item in normalized_other_fees), 2)
    draft["total_amount"] = round(
        _num(draft.get("rent_amount")) +
        _num(draft.get("water_fee")) +
        _num(draft.get("electric_fee")) +
        _num(draft.get("other_fee")),
        2,
    )

    missing_required = []
    if _num(contract.get("water_unit_price")) > 0 and draft.get("water_curr") is None:
        missing_required.append("水表本月读数")
    if _num(contract.get("electric_unit_price")) > 0 and draft.get("electric_curr") is None:
        missing_required.append("电表本月读数")
    if missing_required:
        return {
            "success": False,
            "message": "缺少必要读数，暂不生成账单。",
            "missing": missing_required,
            "draft": draft_payload,
        }

    adjusted_draft_payload = {
        **draft_payload,
        "draft": draft,
    }
    receipt_image = _receipt_payload_from_draft(adjusted_draft_payload)
    overwrite_existing = bool(existing)
    should_overwrite = overwrite_existing or _bool(overwrite) or bool(remove_fee_names) or clear_other_fee_requested
    action_args = {
        "existing_bill_id": existing.get("id") if existing else None,
        "contract_id": contract.get("id"),
        "month": month,
        "overwrite": should_overwrite,
        "draft": draft,
    }
    action_label_prefix = "覆盖"
    if clear_other_fee_requested:
        action_label_prefix = "清空其他费用并覆盖"
    elif remove_fee_names:
        action_label_prefix = "删除" + "、".join(remove_fee_names) + "并覆盖"
    elif not overwrite_existing:
        action_label_prefix = "保存"
    action = _pending_action(
        "create_bill",
        f"{action_label_prefix}{contract.get('room_number')} {month} 账单，合计 {_money(draft.get('total_amount'))}",
        "confirm_create_bill",
        action_args,
        {
            "room_number": contract.get("room_number"),
            "tenant_name": contract.get("tenant_name"),
            "month": month,
            "total_amount": _num(draft.get("total_amount")),
            "other_fee_details": normalized_other_fees,
            "overwrite": should_overwrite,
            "existing_total_amount": _num(existing.get("receivable")) if existing else None,
            "existing_status": existing.get("status") if existing else None,
            "remove_other_fee_names": remove_fee_names,
            "clear_other_fees": clear_other_fee_requested,
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "bill_prepared",
        "month": month,
        "draft": adjusted_draft_payload,
        "existing_bill": existing if existing else None,
        "pending_action": action,
        "receipt_image": receipt_image,
        "suggested_actions": [
            {
                "id": "keep_existing_bill",
                "label": "保留旧账单",
                "prompt": "取消覆盖，保留现有账单。",
            }
        ] if overwrite_existing else [],
        "message": "检测到已有账单，新账单草稿已准备，请用户确认是否覆盖。" if overwrite_existing else "账单草稿已准备，请用户确认后再保存。",
    }


def confirm_create_bill(
    contract_id: Any,
    month: Any,
    draft: Dict[str, Any],
    existing_bill_id: Any = None,
    overwrite: Any = False,
) -> Dict[str, Any]:
    month = _normalize_month(month)
    existing_id = _int_or_none(existing_bill_id)
    other_fee_details = _normalize_other_fee_details(
        draft.get("other_fee_details"),
        draft.get("other_fee"),
    )
    other_fee_total = round(sum(_num(item.get("amount")) for item in other_fee_details), 2)
    other_fee_details_json = json.dumps(other_fee_details, ensure_ascii=False)
    if existing_id and _bool(overwrite):
        db.update_bill(
            existing_id,
            contract_id,
            month,
            _num(draft.get("rent_amount")),
            _num(draft.get("water_fee")),
            _num(draft.get("electric_fee")),
            other_fee_total,
            "AI助手确认更新账单",
            draft.get("water_last"),
            draft.get("water_curr"),
            draft.get("electric_last"),
            draft.get("electric_curr"),
            draft.get("water_photo"),
            draft.get("electric_photo"),
            other_fee_details_json,
        )
        bill_id = existing_id
    else:
        bill_id = db.add_bill(
            contract_id,
            month,
            _num(draft.get("rent_amount")),
            _num(draft.get("water_fee")),
            _num(draft.get("electric_fee")),
            other_fee_total,
            "AI助手确认生成账单",
            draft.get("water_last") or 0,
            draft.get("water_curr"),
            draft.get("electric_last") or 0,
            draft.get("electric_curr"),
            draft.get("water_photo") or "",
            draft.get("electric_photo") or "",
            other_fee_details_json,
        )

    db.update_bill_status(bill_id, "pending")
    bill = db.get_bill(bill_id)
    return {
        "success": True,
        "action": "bill_updated" if existing_id and _bool(overwrite) else "bill_created",
        "month": month,
        "bill": bill,
        "receipt_image": _receipt_payload_from_bill(bill) if bill else None,
    }


def _resolve_contract_for_update(
    contract_id: Any = None,
    room_number: Any = None,
    building_id: Any = None,
    tenant_name: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    return _resolve_active_contract(contract_id, room_number, tenant_name, building_id)


def _normalize_contract_date(value: Any, allow_empty: bool = False) -> tuple[Optional[str], str]:
    text = str(value or "").strip()
    if not text and allow_empty:
        return "", ""
    if not text:
        return None, "不能为空"
    text = text.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    try:
        normalized = datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
        return normalized, ""
    except Exception:
        return None, "日期格式应为 YYYY-MM-DD"


def _meter_binding_text(meter_id: Any) -> str:
    mid = _int_or_none(meter_id)
    if not mid:
        return "未绑定"
    meter = db.get_meter(mid) or {}
    return str(meter.get("meter_no") or ("表具 ID " + str(mid)))


def _room_status_label(status: Any) -> str:
    text = str(status or "").strip()
    if text == "rented":
        return "在租"
    if text == "idle":
        return "闲置"
    return text or "未填写"


def _room_change_text(field: str, value: Any) -> str:
    if field == "status":
        return _room_status_label(value)
    if field == "floor":
        return str(value or "未填写") + " 楼"
    return str(value or "未填写")


def _meter_type_label(meter_type: Any) -> str:
    text = str(meter_type or "").strip().lower()
    if text in {"water", "水", "水表"}:
        return "水表"
    if text in {"electric", "电", "电表"}:
        return "电表"
    return str(meter_type or "未填写")


def _meter_change_text(field: str, value: Any) -> str:
    if field == "type":
        return _meter_type_label(value)
    if field == "init_reading":
        return _money(value) if isinstance(value, (int, float)) else str(value or "未填写")
    return str(value or "未填写")


def _contract_change_text(field: str, value: Any) -> str:
    if field in {"monthly_rent", "water_unit_price", "electric_unit_price", "deposit"}:
        return "¥" + _money(value)
    if field in {"water_meter_id", "electric_meter_id"}:
        return _meter_binding_text(value)
    if field == "other_fee_details":
        return _other_fee_details_text(value)
    return str(value or "未填写")


def _validate_contract_changes(
    contract: Dict[str, Any],
    requested: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], str]:
    changes: Dict[str, Any] = {}
    number_fields = {"monthly_rent", "water_unit_price", "electric_unit_price", "deposit"}
    meter_fields = {"water_meter_id": "water", "electric_meter_id": "electric"}

    for field, raw in requested.items():
        if field in number_fields:
            value = _float_or_none(raw)
            if value is None or value < 0:
                return None, CONTRACT_UPDATE_LABELS[field] + "应为大于等于 0 的数字"
            changes[field] = round(value, 4)
        elif field in {"start_date", "end_date"}:
            value, error = _normalize_contract_date(raw, allow_empty=field == "end_date")
            if error:
                return None, CONTRACT_UPDATE_LABELS[field] + error
            changes[field] = value
        elif field in meter_fields:
            mid = _int_or_none(raw)
            if not mid:
                return None, CONTRACT_UPDATE_LABELS[field] + "缺少有效表具 ID"
            meter = db.get_meter(mid)
            if not meter:
                return None, CONTRACT_UPDATE_LABELS[field] + "对应的表具不存在"
            if str(meter.get("type") or "") != meter_fields[field]:
                return None, CONTRACT_UPDATE_LABELS[field] + "的表具类型不正确"
            if _int_or_none(meter.get("room_id")) != _int_or_none(contract.get("room_id")):
                return None, CONTRACT_UPDATE_LABELS[field] + "不属于该合同房间"
            changes[field] = mid
        elif field == "other_fee_details":
            changes[field] = _normalize_other_fee_details(raw)

    if not changes:
        return None, "请说明要修改月租、水电单价、押金、合同日期、表具绑定或其它费用中的哪一项"

    start_date = str(changes.get("start_date", contract.get("start_date") or ""))
    end_date = str(changes.get("end_date", contract.get("end_date") or ""))
    if not start_date:
        return None, "合同开始日期不能为空"
    if end_date and end_date < start_date:
        return None, "合同结束日期不能早于开始日期"
    return changes, ""


def contract_update_from_ai(
    contract_id: Any = None,
    room_number: Any = None,
    building_id: Any = None,
    tenant_name: Any = None,
    start_date: Any = _UNSET,
    end_date: Any = _UNSET,
    monthly_rent: Any = _UNSET,
    water_unit_price: Any = _UNSET,
    electric_unit_price: Any = _UNSET,
    deposit: Any = _UNSET,
    water_meter_id: Any = _UNSET,
    electric_meter_id: Any = _UNSET,
    other_fee_details: Any = _UNSET,
) -> Dict[str, Any]:
    contract, error = _resolve_contract_for_update(contract_id, room_number, building_id, tenant_name)
    if not contract:
        return {"success": False, "message": error}

    supplied = {
        "start_date": start_date,
        "end_date": end_date,
        "monthly_rent": monthly_rent,
        "water_unit_price": water_unit_price,
        "electric_unit_price": electric_unit_price,
        "deposit": deposit,
        "water_meter_id": water_meter_id,
        "electric_meter_id": electric_meter_id,
        "other_fee_details": other_fee_details,
    }
    requested = {key: value for key, value in supplied.items() if value is not _UNSET}
    changes, error = _validate_contract_changes(contract, requested)
    if not changes:
        return {"success": False, "message": error}

    actual_changes = {}
    change_items = []
    for field, after in changes.items():
        before = contract.get(field)
        if field in {"monthly_rent", "water_unit_price", "electric_unit_price", "deposit"}:
            unchanged = abs(_num(before) - _num(after)) < 0.0001
        elif field == "other_fee_details":
            unchanged = _normalize_other_fee_details(before) == _normalize_other_fee_details(after)
        else:
            unchanged = str(before or "") == str(after or "")
        if unchanged:
            continue
        actual_changes[field] = after
        change_items.append({
            "field": field,
            "label": CONTRACT_UPDATE_LABELS[field],
            "before": _contract_change_text(field, before),
            "after": _contract_change_text(field, after),
        })

    if not actual_changes:
        return {"success": False, "message": "合同当前内容已经是你指定的值，无需修改"}

    action = _pending_action(
        "update_contract",
        "修改{} {}合同：{}".format(
            contract.get("building_name") or "",
            contract.get("room_number") or "",
            "、".join(item["label"] for item in change_items),
        ).strip(),
        "confirm_update_contract",
        {"contract_id": contract.get("id"), "changes": actual_changes},
        {
            "contract_id": contract.get("id"),
            "building_name": contract.get("building_name"),
            "room_number": contract.get("room_number"),
            "tenant_name": contract.get("tenant_name"),
            "change_items": change_items,
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "contract_update_prepared",
        "contract": contract,
        "changes": actual_changes,
        "pending_action": action,
        "message": "合同修改内容已准备，请用户确认后再写入。",
    }


def contract_create_from_ai(
    tenant_id: Any = None,
    tenant_name: Any = None,
    tenant_phone: Any = None,
    tenant_id_card: Any = None,
    room_id: Any = None,
    room_number: Any = None,
    building_id: Any = None,
    building_name: Any = None,
    start_date: Any = None,
    end_date: Any = "",
    monthly_rent: Any = None,
    water_unit_price: Any = 0,
    electric_unit_price: Any = 0,
    deposit: Any = 0,
    water_meter_id: Any = None,
    electric_meter_id: Any = None,
    other_fee_details: Any = None,
) -> Dict[str, Any]:
    resolved_building_id, resolved_building_name, building_error = _resolve_building_for_contract(building_id, building_name)
    form_values = {
        "building_name": resolved_building_name or str(building_name or "").strip(),
        "tenant_name": str(tenant_name or "").strip(),
        "tenant_phone": str(tenant_phone or "").strip(),
        "tenant_id_card": str(tenant_id_card or "").strip(),
        "room_number": str(room_number or "").strip(),
        "start_date": str(start_date or "").strip(),
        "end_date": str(end_date or "").strip(),
        "monthly_rent": "" if monthly_rent is None else monthly_rent,
        "water_unit_price": "" if water_unit_price in {None, ""} else water_unit_price,
        "electric_unit_price": "" if electric_unit_price in {None, ""} else electric_unit_price,
        "deposit": "" if deposit in {None, ""} else deposit,
        "other_fee_details": other_fee_details or "",
    }
    if building_error:
        return {
            "success": False,
            "requires_form": True,
            "message": building_error,
            "form_action": _contract_create_form_action(form_values, ["building_name"], building_error),
        }

    preview_room = None
    if _int_or_none(room_id) or form_values["room_number"]:
        preview_room, _ = _resolve_room_for_contract(room_id, room_number, resolved_building_id)
        if preview_room:
            resolved_building_id = _int_or_none(preview_room.get("building_id")) or resolved_building_id
            resolved_building_name = str(preview_room.get("building_name") or resolved_building_name or "")
            form_values.update({
                "building_id": "" if resolved_building_id is None else str(resolved_building_id),
                "building_name": resolved_building_name,
                "room_id": "" if preview_room.get("id") is None else str(preview_room.get("id")),
                "room_number": str(preview_room.get("room_number") or form_values["room_number"]),
            })
    elif resolved_building_id:
        form_values["building_id"] = str(resolved_building_id)

    missing_fields = []
    if not _int_or_none(tenant_id) and not form_values["tenant_name"]:
        missing_fields.append("tenant_name")
    if not _int_or_none(room_id) and not form_values["room_number"]:
        missing_fields.append("room_number")
    if not form_values["start_date"]:
        missing_fields.append("start_date")
    if monthly_rent is None or monthly_rent == "":
        missing_fields.append("monthly_rent")
    if missing_fields:
        return {
            "success": False,
            "requires_form": True,
            "message": "新建合同还缺少必要信息，请填写表单。",
            "form_action": _contract_create_form_action(form_values, missing_fields, "新建合同还缺少必要信息，请补充后提交。"),
        }

    tenant, tenant_error = _resolve_tenant_for_contract(tenant_id, tenant_name, resolved_building_id)
    room, room_error = _resolve_room_for_contract(room_id, room_number, resolved_building_id)
    if not room:
        return {
            "success": False,
            "requires_form": True,
            "message": room_error,
            "form_action": _contract_create_form_action(form_values, ["room_number"], room_error),
        }
    if not tenant:
        if tenant_error.startswith("匹配到多个"):
            return {
                "success": False,
                "requires_form": True,
                "message": tenant_error,
                "form_action": _contract_create_form_action(form_values, ["tenant_name"], tenant_error),
            }
        tenant = {
            "id": None,
            "name": form_values["tenant_name"],
            "phone": form_values["tenant_phone"],
            "id_card": form_values["tenant_id_card"],
            "building_id": resolved_building_id or room.get("building_id"),
            "room_id": str(room.get("id")),
            "status": "active",
        }

    existing_contract = _find_active_contract(room_number=room.get("room_number"), building_id=room.get("building_id"))
    if existing_contract and _int_or_none(existing_contract.get("room_id")) == _int_or_none(room.get("id")):
        return {
            "success": False,
            "message": "该房间已有有效合同，不能直接新建合同；请先处理原合同。",
            "existing_contract": _contract_summary(existing_contract),
        }

    normalized_start, error = _normalize_contract_date(start_date)
    if error:
        return {"success": False, "message": "合同开始" + error}
    normalized_end, error = _normalize_contract_date(end_date, allow_empty=True)
    if error:
        return {"success": False, "message": "合同结束" + error}
    if normalized_end and normalized_end < normalized_start:
        return {"success": False, "message": "合同结束日期不能早于开始日期"}

    rent = _float_or_none(monthly_rent)
    if rent is None or rent < 0:
        return {"success": False, "message": "请提供有效月租金额"}
    water_price = _float_or_none(water_unit_price)
    electric_price = _float_or_none(electric_unit_price)
    deposit_amount = _float_or_none(deposit)
    if water_price is None or water_price < 0:
        return {"success": False, "message": "水费单价应为大于等于 0 的数字"}
    if electric_price is None or electric_price < 0:
        return {"success": False, "message": "电费单价应为大于等于 0 的数字"}
    if deposit_amount is None or deposit_amount < 0:
        return {"success": False, "message": "保证金应为大于等于 0 的数字"}
    normalized_other_fees = _normalize_other_fee_details(other_fee_details)

    water_mid, error = _validate_contract_meter(room.get("id"), water_meter_id, "water", "水表")
    if error:
        return {"success": False, "message": error}
    electric_mid, error = _validate_contract_meter(room.get("id"), electric_meter_id, "electric", "电表")
    if error:
        return {"success": False, "message": error}

    contract_payload = {
        "tenant_id": tenant.get("id"),
        "tenant_name": tenant.get("name"),
        "tenant_phone": tenant.get("phone"),
        "tenant_id_card": tenant.get("id_card"),
        "room_id": room.get("id"),
        "start_date": normalized_start,
        "end_date": normalized_end or "",
        "monthly_rent": round(rent, 2),
        "water_unit_price": round(water_price, 4),
        "electric_unit_price": round(electric_price, 4),
        "deposit": round(deposit_amount, 2),
        "water_meter_id": water_mid,
        "electric_meter_id": electric_mid,
        "other_fee_details": normalized_other_fees,
    }
    change_items = [
        {"field": "start_date", "label": "合同开始", "before": "未创建", "after": normalized_start},
        {"field": "end_date", "label": "合同结束", "before": "未创建", "after": normalized_end or "未填写"},
        {"field": "monthly_rent", "label": "月租", "before": "未创建", "after": _contract_change_text("monthly_rent", rent)},
        {"field": "deposit", "label": "保证金", "before": "未创建", "after": _contract_change_text("deposit", deposit_amount)},
        {"field": "water_unit_price", "label": "水费单价", "before": "未创建", "after": _contract_change_text("water_unit_price", water_price)},
        {"field": "electric_unit_price", "label": "电费单价", "before": "未创建", "after": _contract_change_text("electric_unit_price", electric_price)},
    ]
    if water_mid:
        change_items.append({"field": "water_meter_id", "label": "水表绑定", "before": "未创建", "after": _contract_change_text("water_meter_id", water_mid)})
    if electric_mid:
        change_items.append({"field": "electric_meter_id", "label": "电表绑定", "before": "未创建", "after": _contract_change_text("electric_meter_id", electric_mid)})
    if normalized_other_fees:
        change_items.append({"field": "other_fee_details", "label": "其它费用", "before": "未创建", "after": _contract_change_text("other_fee_details", normalized_other_fees)})

    action = _pending_action(
        "create_contract",
        "新建{} {}合同：{}".format(room.get("building_name") or "", room.get("room_number") or "", tenant.get("name") or "").strip(),
        "confirm_create_contract",
        {"contract": contract_payload},
        {
            "building_name": room.get("building_name"),
            "room_number": room.get("room_number"),
            "tenant_name": tenant.get("name"),
            "tenant_phone": tenant.get("phone"),
            "tenant_id_card": tenant.get("id_card"),
            "room_type": room.get("room_type"),
            "change_items": change_items,
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "contract_create_prepared",
        "contract": contract_payload,
        "tenant": tenant,
        "room": room,
        "pending_action": action,
        "message": "新建合同内容已准备，请用户确认后再写入。",
    }


def confirm_create_contract(contract: Any = None) -> Dict[str, Any]:
    if not isinstance(contract, dict):
        return {"success": False, "message": "确认新建合同时缺少合同内容"}
    room = db.get_room(_int_or_none(contract.get("room_id")))
    if not room:
        return {"success": False, "message": "确认新建合同时未找到房间"}
    existing_contract = _find_active_contract(room_number=room.get("room_number"), building_id=room.get("building_id"))
    if existing_contract and _int_or_none(existing_contract.get("room_id")) == _int_or_none(room.get("id")):
        return {"success": False, "message": "该房间已有有效合同，无法新建。"}

    tenant = db.get_tenant(_int_or_none(contract.get("tenant_id")))
    if not tenant:
        tenant = _create_tenant_for_contract(
            tenant_name=contract.get("tenant_name"),
            tenant_phone=contract.get("tenant_phone"),
            tenant_id_card=contract.get("tenant_id_card"),
            building_id=room.get("building_id"),
            room_id=room.get("id"),
        )
    if not tenant:
        return {"success": False, "message": "确认新建合同时未找到租户"}

    start_date, error = _normalize_contract_date(contract.get("start_date"))
    if error:
        return {"success": False, "message": "合同开始" + error}
    end_date, error = _normalize_contract_date(contract.get("end_date"), allow_empty=True)
    if error:
        return {"success": False, "message": "合同结束" + error}
    if end_date and end_date < start_date:
        return {"success": False, "message": "合同结束日期不能早于开始日期"}

    water_mid, error = _validate_contract_meter(room.get("id"), contract.get("water_meter_id"), "water", "水表")
    if error:
        return {"success": False, "message": error}
    electric_mid, error = _validate_contract_meter(room.get("id"), contract.get("electric_meter_id"), "electric", "电表")
    if error:
        return {"success": False, "message": error}
    other_fee_details = _normalize_other_fee_details(contract.get("other_fee_details"))
    other_fee_details_json = json.dumps(other_fee_details, ensure_ascii=False)

    contract_id = db.add_contract(
        tenant.get("id"),
        room.get("id"),
        start_date,
        end_date or "",
        _num(contract.get("monthly_rent")),
        _num(contract.get("water_unit_price")),
        _num(contract.get("electric_unit_price")),
        _num(contract.get("deposit")),
        "",
        "active",
        water_mid,
        electric_mid,
        other_fee_details_json,
    )
    db.update_tenant(
        tenant.get("id"),
        tenant.get("name") or "",
        str(contract.get("tenant_phone") or tenant.get("phone") or ""),
        str(contract.get("tenant_id_card") or tenant.get("id_card") or ""),
        "active",
        room.get("building_id"),
        str(room.get("id")),
    )
    created = db.get_contract(contract_id)
    return {
        "success": True,
        "action": "contract_created",
        "contract_id": contract_id,
        "contract": created,
        "message": "合同已新建",
    }


def confirm_update_contract(contract_id: Any, changes: Any = None) -> Dict[str, Any]:
    cid = _int_or_none(contract_id)
    contract = db.get_contract(cid) if cid else None
    if not contract:
        return {"success": False, "message": "确认修改时未找到该合同"}
    if not isinstance(changes, dict):
        return {"success": False, "message": "确认修改时缺少合同变更内容"}

    normalized, error = _validate_contract_changes(contract, changes)
    if not normalized:
        return {"success": False, "message": error}

    db.update_contract(
        cid,
        tenant_id=contract.get("tenant_id"),
        room_id=contract.get("room_id"),
        start_date=normalized.get("start_date", contract.get("start_date") or ""),
        end_date=normalized.get("end_date", contract.get("end_date") or ""),
        monthly_rent=normalized.get("monthly_rent", contract.get("monthly_rent") or 0),
        water_price=normalized.get("water_unit_price", contract.get("water_unit_price") or 0),
        electric_price=normalized.get("electric_unit_price", contract.get("electric_unit_price") or 0),
        deposit=normalized.get("deposit", contract.get("deposit") or 0),
        contract_file=contract.get("contract_file") or "",
        status=contract.get("status") or "active",
        water_meter_id=normalized.get("water_meter_id", contract.get("water_meter_id")),
        electric_meter_id=normalized.get("electric_meter_id", contract.get("electric_meter_id")),
        other_fee_details=json.dumps(
            _normalize_other_fee_details(normalized.get("other_fee_details", contract.get("other_fee_details"))),
            ensure_ascii=False,
        ),
    )
    updated = db.get_contract(cid)
    return {
        "success": True,
        "action": "contract_updated",
        "contract_id": cid,
        "changed_fields": list(normalized.keys()),
        "contract": updated,
        "message": "合同已更新",
    }


def _contract_summary(contract: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "contract_id": contract.get("id"),
        "building_name": contract.get("building_name"),
        "room_number": contract.get("room_number"),
        "room_type": contract.get("room_type"),
        "tenant_name": contract.get("tenant_name"),
        "tenant_phone": contract.get("tenant_phone"),
        "start_date": contract.get("start_date"),
        "end_date": contract.get("end_date"),
        "monthly_rent": contract.get("monthly_rent"),
        "deposit": contract.get("deposit"),
        "water_unit_price": contract.get("water_unit_price"),
        "electric_unit_price": contract.get("electric_unit_price"),
        "other_fee_details": _contract_other_fee_details(contract),
        "other_fee_total": _contract_other_fee_total(contract),
        "water_meter_id": contract.get("water_meter_id"),
        "electric_meter_id": contract.get("electric_meter_id"),
        "status": contract.get("status"),
    }


def contract_tenant_get_contract_detail(
    contract_id: Any = None,
    room_number: Any = None,
    tenant_name: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    contract, error = _resolve_active_contract(contract_id, room_number, tenant_name, building_id)
    if not contract:
        return {"found": False, "message": error}
    meters = db.get_meters(contract.get("room_id")) or []
    return {
        "found": True,
        "contract": _contract_summary(contract),
        "raw_contract": contract,
        "meters": meters,
    }


def contract_tenant_list_active_contracts(
    building_id: Any = None,
    tenant_name: Any = None,
    room_number: Any = None,
) -> Dict[str, Any]:
    rows = db.get_contracts(True, _int_or_none(building_id)) or []
    tenant_text = str(tenant_name or "").strip()
    room_text = str(room_number or "").strip()
    if tenant_text:
        rows = [item for item in rows if tenant_text in str(item.get("tenant_name") or "")]
    if room_text:
        rows = [item for item in rows if room_text in str(item.get("room_number") or "")]
    return {
        "count": len(rows),
        "rows": [_contract_summary(item) for item in rows[:100]],
    }


def contract_tenant_get_room_tenant(room_number: Any = None, building_id: Any = None, tenant_name: Any = None) -> Dict[str, Any]:
    contract, error = _resolve_active_contract(room_number=room_number, tenant_name=tenant_name, building_id=building_id)
    if not contract:
        return {"found": False, "message": error or "该房间当前没有有效合同或未找到房间"}
    return {"found": True, "contract": _contract_summary(contract), "raw_contract": contract}


def contract_tenant_get_contract_meter_binding(
    room_number: Any = None,
    building_id: Any = None,
    tenant_name: Any = None,
    contract_id: Any = None,
) -> Dict[str, Any]:
    contract, error = _resolve_active_contract(contract_id=contract_id, room_number=room_number, tenant_name=tenant_name, building_id=building_id)
    if not contract:
        return {"found": False, "message": error or "该房间当前没有有效合同或未找到房间"}
    meters = db.get_meters(contract.get("room_id")) or []
    return {
        "found": True,
        "contract": _contract_summary(contract),
        "raw_contract": contract,
        "meters": meters,
        "binding": {
            "water_meter_id": contract.get("water_meter_id"),
            "electric_meter_id": contract.get("electric_meter_id"),
        },
    }


def contract_tenant_list_expiring_contracts(days: Any = 30, building_id: Any = None) -> Dict[str, Any]:
    limit_days = max(_int_or_none(days) or 30, 0)
    today = date.today()
    rows = []
    for contract in db.get_contracts(True, _int_or_none(building_id)) or []:
        end_date = str(contract.get("end_date") or "").strip()
        if not end_date:
            continue
        try:
            end = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        left = (end - today).days
        if 0 <= left <= limit_days:
            item = dict(contract)
            item["days_left"] = left
            rows.append(item)
    rows.sort(key=lambda x: x["days_left"])
    return {"days": limit_days, "count": len(rows), "rows": rows}


def contract_tenant_list_empty_rooms(building_id: Any = None) -> Dict[str, Any]:
    rooms = db.get_rooms(_int_or_none(building_id)) or []
    active_room_ids = {c.get("room_id") for c in db.get_contracts(True, _int_or_none(building_id)) or []}
    rows = []
    for room in rooms:
        if room.get("id") not in active_room_ids:
            rows.append(room)
    return {"count": len(rows), "rows": rows}


def _room_with_building(room: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(room or {})
    if result.get("building_name"):
        return result
    bid = _int_or_none(result.get("building_id"))
    building = next((item for item in (db.get_buildings() or []) if _int_or_none(item.get("id")) == bid), None)
    if building:
        result["building_name"] = building.get("name")
    return result


def _resolve_room_for_update(
    room_id: Any = None,
    room_number: Any = None,
    building_id: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    rid = _int_or_none(room_id)
    if rid:
        room = db.get_room(rid)
        return (_room_with_building(room), "") if room else (None, "未找到该房间")
    room, error = _resolve_room_for_contract(room_id, room_number, building_id)
    return (_room_with_building(room), "") if room else (None, error)


def _room_status_label(status: Any) -> str:
    text = str(status or "").strip()
    if text == "rented":
        return "在租"
    if text == "idle":
        return "闲置"
    return text or "未填写"


def _room_change_text(field: str, value: Any) -> str:
    if field == "status":
        return _room_status_label(value)
    if field == "floor":
        return str(value or "未填写") + " 楼"
    return str(value or "未填写")


def _validate_room_changes(room: Dict[str, Any], requested: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    changes: Dict[str, Any] = {}
    for field, raw in requested.items():
        if field == "room_number":
            value = str(raw or "").strip()
            if not value:
                return None, "房间号不能为空"
            changes[field] = value
        elif field == "room_type":
            value = str(raw or "").strip()
            if not value:
                return None, "户型不能为空"
            if len(value) > 32:
                return None, "户型不能超过 32 个字符"
            changes[field] = value
        elif field == "floor":
            value = _int_or_none(raw)
            if value is None or value < 0 or value > 200:
                return None, "楼层应为 0 到 200 之间的整数"
            changes[field] = value
        elif field == "status":
            text = str(raw or "").strip().lower()
            status_map = {"idle": "idle", "闲置": "idle", "空置": "idle", "rented": "rented", "在租": "rented", "已租": "rented"}
            if text not in status_map:
                return None, "房间状态只能是闲置或在租"
            changes[field] = status_map[text]

    if not changes:
        return None, "请说明要修改房间号、楼层、户型或状态中的哪一项"

    if "room_number" in changes:
        building_id = _int_or_none(room.get("building_id"))
        duplicate = [
            item for item in db.get_rooms(building_id) or []
            if str(item.get("room_number") or "").strip() == changes["room_number"]
            and _int_or_none(item.get("id")) != _int_or_none(room.get("id"))
        ]
        if duplicate:
            return None, "该楼栋已存在同名房间号"
    return changes, ""


def room_update_from_ai(
    room_id: Any = None,
    room_number: Any = None,
    building_id: Any = None,
    new_room_number: Any = _UNSET,
    room_type: Any = _UNSET,
    floor: Any = _UNSET,
    status: Any = _UNSET,
) -> Dict[str, Any]:
    room, error = _resolve_room_for_update(room_id, room_number, building_id)
    if not room:
        return {"success": False, "message": error}

    supplied = {"room_number": new_room_number, "room_type": room_type, "floor": floor, "status": status}
    requested = {key: value for key, value in supplied.items() if value is not _UNSET}
    changes, error = _validate_room_changes(room, requested)
    if not changes:
        return {"success": False, "message": error}

    actual_changes = {}
    change_items = []
    for field, after in changes.items():
        before = room.get(field)
        unchanged = _int_or_none(before) == _int_or_none(after) if field == "floor" else str(before or "") == str(after or "")
        if unchanged:
            continue
        actual_changes[field] = after
        change_items.append({
            "field": field,
            "label": ROOM_UPDATE_LABELS[field],
            "before": _room_change_text(field, before),
            "after": _room_change_text(field, after),
        })

    if not actual_changes:
        return {"success": False, "message": "房间当前内容已经是你指定的值，无需修改"}

    action = _pending_action(
        "update_room",
        "修改{} {}：{}".format(room.get("building_name") or "", room.get("room_number") or "", "、".join(item["label"] for item in change_items)).strip(),
        "confirm_update_room",
        {"room_id": room.get("id"), "changes": actual_changes},
        {
            "building_name": room.get("building_name"),
            "room_number": room.get("room_number"),
            "room_type": room.get("room_type"),
            "change_items": change_items,
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "room_update_prepared",
        "room": room,
        "changes": actual_changes,
        "pending_action": action,
        "message": "房间修改内容已准备，请用户确认后再写入。",
    }


def confirm_update_room(room_id: Any, changes: Any = None) -> Dict[str, Any]:
    room = db.get_room(_int_or_none(room_id))
    if not room:
        return {"success": False, "message": "确认修改时未找到该房间"}
    if not isinstance(changes, dict):
        return {"success": False, "message": "确认修改时缺少房间变更内容"}
    normalized, error = _validate_room_changes(_room_with_building(room), changes)
    if not normalized:
        return {"success": False, "message": error}
    db.update_room(
        room.get("id"),
        room.get("building_id"),
        normalized.get("room_number", room.get("room_number") or ""),
        normalized.get("floor", room.get("floor") or 1),
        normalized.get("status", room.get("status") or "idle"),
        normalized.get("room_type", room.get("room_type") or "单间"),
    )
    updated = _room_with_building(db.get_room(room.get("id")) or {})
    return {
        "success": True,
        "action": "room_updated",
        "room_id": room.get("id"),
        "changed_fields": list(normalized.keys()),
        "room": updated,
        "message": "房间已更新",
    }


def _resolve_meter_for_update(
    meter_id: Any = None,
    room_number: Any = None,
    meter_type: Any = None,
    building_id: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    mid = _int_or_none(meter_id)
    if mid:
        meter = db.get_meter(mid)
        return (meter, "") if meter else (None, "未找到该表具")

    normalized_type = _normalize_meter_type(meter_type)
    if not normalized_type:
        return None, "请说明要修改水表还是电表"
    room, error = _resolve_room_for_update(room_number=room_number, building_id=building_id)
    if not room:
        return None, error
    matches = [item for item in db.get_meters(room.get("id"), room.get("building_id"), normalized_type) or [] if str(item.get("type") or "") == normalized_type]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        names = "、".join("{}(ID {})".format(item.get("meter_no") or _meter_type_label(item.get("type")), item.get("id")) for item in matches[:8])
        return None, "匹配到多个表具，请补充表具 ID：" + names
    return None, "未找到该房间对应的" + _meter_type_label(normalized_type)


def _validate_meter_changes(meter: Dict[str, Any], requested: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], str]:
    changes: Dict[str, Any] = {}
    for field, raw in requested.items():
        if field == "meter_no":
            changes[field] = str(raw or "").strip()
        elif field == "init_reading":
            value = _float_or_none(raw)
            if value is None or value < 0:
                return None, "初始读数应为大于等于 0 的数字"
            changes[field] = round(value, 4)
    if not changes:
        return None, "请说明要修改表号或初始读数"
    return changes, ""


def _meter_change_text(field: str, value: Any) -> str:
    if field == "init_reading":
        return _money(value)
    return str(value or "未填写")


def meter_update_from_ai(
    meter_id: Any = None,
    room_number: Any = None,
    meter_type: Any = None,
    building_id: Any = None,
    meter_no: Any = _UNSET,
    init_reading: Any = _UNSET,
) -> Dict[str, Any]:
    meter, error = _resolve_meter_for_update(meter_id, room_number, meter_type, building_id)
    if not meter:
        return {"success": False, "message": error}
    supplied = {"meter_no": meter_no, "init_reading": init_reading}
    requested = {key: value for key, value in supplied.items() if value is not _UNSET}
    changes, error = _validate_meter_changes(meter, requested)
    if not changes:
        return {"success": False, "message": error}

    actual_changes = {}
    change_items = []
    for field, after in changes.items():
        before = meter.get(field)
        unchanged = abs(_num(before) - _num(after)) < 0.0001 if field == "init_reading" else str(before or "") == str(after or "")
        if unchanged:
            continue
        actual_changes[field] = after
        change_items.append({
            "field": field,
            "label": METER_UPDATE_LABELS[field],
            "before": _meter_change_text(field, before),
            "after": _meter_change_text(field, after),
        })
    if not actual_changes:
        return {"success": False, "message": "表具当前内容已经是你指定的值，无需修改"}

    action = _pending_action(
        "update_meter",
        "修改{} {} {}：{}".format(
            meter.get("building_name") or "",
            meter.get("room_number") or "",
            _meter_type_label(meter.get("type")),
            "、".join(item["label"] for item in change_items),
        ).strip(),
        "confirm_update_meter",
        {"meter_id": meter.get("id"), "changes": actual_changes},
        {
            "building_name": meter.get("building_name"),
            "room_number": meter.get("room_number"),
            "meter_type": meter.get("type"),
            "meter_type_label": _meter_type_label(meter.get("type")),
            "meter_no": meter.get("meter_no"),
            "change_items": change_items,
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "meter_update_prepared",
        "meter": meter,
        "changes": actual_changes,
        "pending_action": action,
        "message": "表具修改内容已准备，请用户确认后再写入。",
    }


def confirm_update_meter(meter_id: Any, changes: Any = None) -> Dict[str, Any]:
    meter = db.get_meter(_int_or_none(meter_id))
    if not meter:
        return {"success": False, "message": "确认修改时未找到该表具"}
    if not isinstance(changes, dict):
        return {"success": False, "message": "确认修改时缺少表具变更内容"}
    normalized, error = _validate_meter_changes(meter, changes)
    if not normalized:
        return {"success": False, "message": error}
    db.update_meter(
        meter.get("id"),
        meter.get("room_id"),
        meter.get("type") or "water",
        normalized.get("meter_no", meter.get("meter_no") or ""),
        normalized.get("init_reading", meter.get("init_reading") or 0),
        None,
    )
    updated = db.get_meter(meter.get("id"))
    return {
        "success": True,
        "action": "meter_updated",
        "meter_id": meter.get("id"),
        "changed_fields": list(normalized.keys()),
        "meter": updated,
        "message": "表具已更新",
    }


def _payment_records(building_id: Any = None) -> List[Dict[str, Any]]:
    rows = []
    for payment in db.get_payments() or []:
        bill = db.get_bill(payment.get("bill_id"))
        if _int_or_none(building_id) and bill and bill.get("building_id") != _int_or_none(building_id):
            continue
        item = dict(payment)
        if bill:
            item.update({
                "building": bill.get("building_name", ""),
                "room_number": bill.get("room_number", ""),
                "tenant": bill.get("tenant_name", ""),
                "bill_total": bill.get("total_amount"),
                "bill_status": bill.get("status"),
            })
        rows.append(item)
    return rows


def payment_list_paid(
    date_range: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> Dict[str, Any]:
    mode = str(date_range or "").strip()
    target_month = _normalize_month(month) if month else _today_month()
    today = date.today().isoformat()
    rows = []
    for payment in _payment_records(building_id):
        pay_date = str(payment.get("pay_date") or "")
        if mode in {"today", "今日", "今天"}:
            if pay_date[:10] != today:
                continue
        else:
            if pay_date[:7] != target_month:
                continue
        rows.append(payment)
    return {
        "date_range": mode or "month",
        "month": target_month if mode not in {"today", "今日", "今天"} else "",
        "count": len(rows),
        "total_paid": round(sum(_num(r.get("amount")) for r in rows), 2),
        "rows": rows,
    }


def payment_list_pending(month: Any = None, building_id: Any = None) -> Dict[str, Any]:
    data = rent_plan_list_month_status(month, building_id)
    rows = [row for row in data["rows"] if _num(row.get("due")) > 0]
    return {"month": data["month"], "count": len(rows), "total_due": round(sum(_num(r.get("due")) for r in rows), 2), "rows": rows}


def payment_check_anomalies(month: Any = None, building_id: Any = None) -> Dict[str, Any]:
    month = _normalize_month(month)
    issues = []
    bills = db.get_bills(month) or []
    if _int_or_none(building_id):
        bills = [bill for bill in bills if bill.get("building_id") == _int_or_none(building_id)]
    for bill in bills:
        payments = _bill_payments(bill.get("id"))
        paid = _payment_total(payments)
        receivable = _num(bill.get("total_amount"))
        if paid > receivable + 0.01:
            issues.append({"level": "warning", "type": "overpaid", "message": "实收金额大于应收金额", "bill": bill, "paid": paid})
        if bill.get("status") == "paid" and paid <= 0:
            issues.append({"level": "info", "type": "paid_without_payment_record", "message": "账单标记已收，但没有收款记录", "bill": bill})
        if bill.get("status") in {"unpaid", "pending_payment"} and paid >= receivable > 0:
            issues.append({"level": "warning", "type": "status_mismatch", "message": "收款已覆盖应收，但账单状态仍待收", "bill": bill, "paid": paid})
        for payment in payments:
            if _num(payment.get("amount")) <= 0:
                issues.append({"level": "warning", "type": "invalid_payment_amount", "message": "收款金额为 0 或负数", "payment": payment, "bill": bill})
    return {"month": month, "issue_count": len(issues), "issues": issues}


def payment_compare_paid_amount(bill_id: Any) -> Dict[str, Any]:
    bill = db.get_bill(_int_or_none(bill_id))
    if not bill:
        return {"found": False, "message": "未找到账单"}
    payments = _bill_payments(bill.get("id"))
    receivable = _num(bill.get("total_amount"))
    paid = _payment_total(payments)
    return {
        "found": True,
        "bill": bill,
        "payments": payments,
        "receivable": receivable,
        "paid": paid,
        "difference": round(receivable - paid, 2),
        "due": round(max(receivable - paid, 0), 2),
        "overpaid": round(max(paid - receivable, 0), 2),
    }


def _resolve_bill_for_payment(
    bill_id: Any = None,
    room_number: Any = None,
    month: Any = None,
    building_id: Any = None,
) -> tuple[Optional[Dict[str, Any]], str]:
    bid = _int_or_none(bill_id)
    if bid:
        bill = db.get_bill(bid)
        return (bill, "") if bill else (None, "未找到该账单")

    room_text = str(room_number or "").strip()
    if not room_text:
        return None, "请说明要确认收款的房间号"

    target_month = _normalize_month(month)
    rows = db.get_bills(target_month) or []
    exact = [row for row in rows if str(row.get("room_number") or "").strip() == room_text]
    target_building_id = _int_or_none(building_id)
    if target_building_id:
        exact = [row for row in exact if _int_or_none(row.get("building_id")) == target_building_id]
    if not exact:
        return None, f"未找到 {target_month} 的 {room_text} 房间账单"
    if len(exact) > 1:
        buildings = "、".join(sorted({str(row.get("building_name") or "未知楼栋") for row in exact}))
        return None, f"房间号 {room_text} 在多个楼栋都有账单，请明确楼栋：{buildings}"
    return exact[0], ""


def payment_confirm_from_ai(
    bill_id: Any = None,
    room_number: Any = None,
    month: Any = None,
    building_id: Any = None,
    amount: Any = None,
    pay_date: Any = None,
    pay_method: Any = "",
    remark: Any = "AI助手确认收款",
) -> Dict[str, Any]:
    bill, error = _resolve_bill_for_payment(bill_id, room_number, month, building_id)
    if not bill:
        return {"success": False, "message": error}

    status = str(bill.get("status") or "")
    if status in {"empty", "draft", "pending", "recorded"}:
        return {
            "success": False,
            "message": f"该账单当前为{_status_label(status)}，请先完成账单发送后再确认收款。",
            "bill": bill,
        }
    if status == "paid":
        return {"success": False, "message": "该账单已经是已收款状态，无需重复确认。", "bill": bill}

    payments = _bill_payments(bill.get("id"))
    receivable = round(_num(bill.get("total_amount")), 2)
    paid = _payment_total(payments)
    due = round(max(receivable - paid, 0), 2)
    if due <= 0:
        return {"success": False, "message": "该账单已没有待收金额，无需重复确认。", "bill": bill}

    payment_amount = due if amount is None or amount == "" else round(_num(amount), 2)
    if payment_amount <= 0:
        return {"success": False, "message": "本次收款金额必须大于 0。", "bill": bill}
    if payment_amount > due + 0.01:
        return {
            "success": False,
            "message": f"本次收款 {_money(payment_amount)} 元超过待收 {_money(due)} 元，请核对金额。",
            "bill": bill,
        }

    payment_date = _normalize_date(pay_date)
    if not payment_date:
        return {"success": False, "message": "收款日期格式不正确，请使用 YYYY-MM-DD。", "bill": bill}

    action_args = {
        "bill_id": bill.get("id"),
        "amount": payment_amount,
        "pay_date": payment_date,
        "pay_method": str(pay_method or ""),
        "remark": str(remark or "AI助手确认收款"),
    }
    action = _pending_action(
        "record_payment",
        f"确认{bill.get('room_number')} {bill.get('billing_month')} 收款 {_money(payment_amount)} 元",
        "confirm_record_payment",
        action_args,
        {
            "building_name": bill.get("building_name"),
            "room_number": bill.get("room_number"),
            "tenant_name": bill.get("tenant_name"),
            "month": bill.get("billing_month"),
            "status_label": _status_label(status),
            "receivable": receivable,
            "paid_amount": paid,
            "due_amount": due,
            "payment_amount": payment_amount,
            "remaining_amount": round(max(due - payment_amount, 0), 2),
            "pay_date": payment_date,
            "pay_method": str(pay_method or ""),
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "payment_prepared",
        "bill": bill,
        "pending_action": action,
        "message": "收款信息已准备，请核对后确认收款。",
    }


def confirm_record_payment(
    bill_id: Any,
    amount: Any,
    pay_date: Any = None,
    pay_method: Any = "",
    remark: Any = "AI助手确认收款",
) -> Dict[str, Any]:
    bill = db.get_bill(_int_or_none(bill_id))
    if not bill:
        return {"success": False, "message": "确认时未找到该账单，请重新查询后再操作。"}
    if str(bill.get("status") or "") == "paid":
        return {"success": False, "message": "该账单已经完成收款，请勿重复确认。", "bill": bill}

    payment_amount = round(_num(amount), 2)
    paid_before = _payment_total(_bill_payments(bill.get("id")))
    receivable = round(_num(bill.get("total_amount")), 2)
    due_before = round(max(receivable - paid_before, 0), 2)
    if payment_amount <= 0:
        return {"success": False, "message": "本次收款金额必须大于 0。", "bill": bill}
    if due_before <= 0:
        return {"success": False, "message": "该账单已没有待收金额，请勿重复确认。", "bill": bill}
    if payment_amount > due_before + 0.01:
        return {
            "success": False,
            "message": f"当前待收仅 {_money(due_before)} 元，原确认金额已不适用，请重新发起收款。",
            "bill": bill,
        }

    payment_date = _normalize_date(pay_date)
    if not payment_date:
        return {"success": False, "message": "收款日期格式不正确，请重新发起收款。", "bill": bill}

    payment_id = db.add_payment(
        bill.get("id"),
        payment_amount,
        payment_date,
        str(pay_method or ""),
        str(remark or "AI助手确认收款"),
    )
    updated_bill = db.get_bill(bill.get("id"))
    paid_after = _payment_total(_bill_payments(bill.get("id")))
    due_after = round(max(receivable - paid_after, 0), 2)
    return {
        "success": True,
        "action": "payment_recorded",
        "message": f"收款成功：{bill.get('room_number')} 本次实收 {_money(payment_amount)} 元。",
        "payment_id": payment_id,
        "bill": updated_bill,
        "payment": {
            "amount": payment_amount,
            "pay_date": payment_date,
            "pay_method": str(pay_method or ""),
            "paid_total": paid_after,
            "due": due_after,
        },
    }


def _tool_schema(name: str, description: str, properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


MONTH_PROP = {"type": "string", "description": "账期，格式 YYYY-MM；不传默认本月"}
BUILDING_PROP = {"type": "integer", "description": "楼栋 ID，可选"}
ROOM_PROP = {"type": "string", "description": "房间号，例如 101"}
TENANT_PROP = {"type": "string", "description": "租户/租客姓名；用户只提到租户时可用"}
BILL_ID_PROP = {"type": "integer", "description": "账单 ID"}
CONTRACT_ID_PROP = {"type": "integer", "description": "合同 ID"}
ROOM_ID_PROP = {"type": "integer", "description": "房间 ID"}
METER_ID_PROP = {"type": "integer", "description": "表具 ID"}
METER_TYPE_PROP = {"type": "string", "enum": ["water", "electric"], "description": "水表 water，电表 electric；不传表示全部"}
OTHER_FEE_DETAILS_PROP = {
    "type": "array",
    "description": "其它费用约定明细，例如网费、卫生费；合同中约定后，生成账单时默认带出",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "费用项目名称，例如网费"},
            "amount": {"type": "number", "description": "该项目每期费用金额"},
        },
        "required": ["name", "amount"],
    },
}

TOOL_SCHEMAS = [
    _tool_schema("rent_plan_list_month_status", "查询指定月份所有房间的收租进度。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("rent_plan_list_uncreated_bills", "查询指定月份有有效合同但尚未录入账单的房间。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("rent_plan_get_room_progress", "解释某房间指定月份账单进度。", {"room_number": ROOM_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}, ["room_number"]),
    _tool_schema("rent_plan_check_anomalies", "检查指定月份收租计划异常。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("meter_reading_list_month_status", "查询指定月份水表或电表读数录入情况。", {"meter_type": METER_TYPE_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("meter_reading_get_room_reading", "查询某房间指定月份水电表读数。", {"room_number": ROOM_PROP, "meter_type": METER_TYPE_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}, ["room_number"]),
    _tool_schema("meter_reading_list_missing", "查询指定月份未录入水表或电表读数的房间。", {"meter_type": METER_TYPE_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("meter_reading_check_anomalies", "检查指定月份水电表读数异常。", {"meter_type": METER_TYPE_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("meter_reading_save_from_ai", "AI助手根据识别结果准备录入某房间某月水表或电表读数。返回待确认操作，不直接写库。", {
        "room_number": ROOM_PROP,
        "meter_type": METER_TYPE_PROP,
        "month": MONTH_PROP,
        "reading": {"type": "number", "description": "识别到的表读数"},
        "image_index": {"type": "integer", "description": "上传图片序号，从 0 开始；多图时用于选择对应照片"},
        "photo": {"type": "string", "description": "表照片 data URL，可选"},
        "building_id": BUILDING_PROP,
        "overwrite": {"type": "boolean", "description": "是否覆盖已有读数，默认 false"},
    }, ["room_number", "meter_type", "month", "reading"]),
    _tool_schema("bill_explain_amount", "根据账单 ID 解释账单金额构成。", {"bill_id": BILL_ID_PROP}, ["bill_id"]),
    _tool_schema("bill_get_bill_detail", "按账单 ID 或房间月份查询账单构成。", {"bill_id": BILL_ID_PROP, "room_number": ROOM_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("bill_generate_draft", "生成账单草稿数据但不保存。", {"contract_id": CONTRACT_ID_PROP, "room_number": ROOM_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("bill_validate_preview", "检查已保存账单或账单草稿预览数据。", {"bill_id": BILL_ID_PROP, "contract_id": CONTRACT_ID_PROP, "room_number": ROOM_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("bill_get_receipt_image_data", "获取 AIChat 渲染账单图片所需的数据。只返回图片数据，不保存账单。", {"bill_id": BILL_ID_PROP, "contract_id": CONTRACT_ID_PROP, "room_number": ROOM_PROP, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("bill_create_from_ai", "AI助手根据已录入读数准备生成或覆盖某房间/某租户某月账单，并返回账单图片数据。返回待确认操作，不直接写库。支持用户对话调整金额、读数、增加或删除其他费用。", {
        "room_number": ROOM_PROP,
        "tenant_name": TENANT_PROP,
        "contract_id": CONTRACT_ID_PROP,
        "month": MONTH_PROP,
        "building_id": BUILDING_PROP,
        "overwrite": {"type": "boolean", "description": "是否覆盖已有账单，默认 false"},
        "rent_amount": {"type": "number", "description": "用户指定的房租金额，可选"},
        "water_fee": {"type": "number", "description": "用户指定的水费金额，可选"},
        "electric_fee": {"type": "number", "description": "用户指定的电费金额，可选"},
        "other_fee": {"type": "number", "description": "兼容旧对话的其他费用汇总，可选；有费用明细时不要使用"},
        "other_fee_details": {
            "type": "array",
            "description": "其他费用明细，例如网费、卫生费；用户提到具体项目时必须逐项传入",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "费用项目名称，例如网费"},
                    "amount": {"type": "number", "description": "该项目费用金额"},
                },
                "required": ["name", "amount"],
            },
        },
        "remove_other_fee_names": {
            "type": "array",
            "description": "要从已有账单其它费用中删除的项目名称，例如网费、卫生费；用于用户要求删除或去掉某项其它费用时",
            "items": {"type": "string"},
        },
        "clear_other_fees": {"type": "boolean", "description": "是否清空已有账单的全部其它费用"},
        "water_curr": {"type": "number", "description": "用户指定的水表本月读数，可选"},
        "electric_curr": {"type": "number", "description": "用户指定的电表本月读数，可选"},
    }),
    _tool_schema("contract_tenant_get_contract_detail", "按合同 ID、房间号或租户姓名查询有效合同详情。", {"contract_id": CONTRACT_ID_PROP, "room_number": ROOM_PROP, "tenant_name": TENANT_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("contract_tenant_list_active_contracts", "查询有效合同列表，可按楼栋、房间号或租户姓名筛选。", {"building_id": BUILDING_PROP, "tenant_name": TENANT_PROP, "room_number": ROOM_PROP}),
    _tool_schema("contract_tenant_get_room_tenant", "查询某房间或某租户当前租客和有效合同。", {"room_number": ROOM_PROP, "tenant_name": TENANT_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("contract_tenant_get_contract_meter_binding", "查询某房间、某租户或某合同关联的水电表。", {"contract_id": CONTRACT_ID_PROP, "room_number": ROOM_PROP, "tenant_name": TENANT_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("contract_tenant_list_expiring_contracts", "查询指定天数内即将到期的合同。", {"days": {"type": "integer", "description": "未来多少天内到期，默认 30"}, "building_id": BUILDING_PROP}),
    _tool_schema("contract_tenant_list_empty_rooms", "查询当前空置房间。", {"building_id": BUILDING_PROP}),
    _tool_schema("contract_update_from_ai", "准备修改现有合同。按合同 ID、楼栋房间或租户姓名定位合同；返回待确认操作，不直接写库。", {
        "contract_id": CONTRACT_ID_PROP,
        "room_number": ROOM_PROP,
        "tenant_name": TENANT_PROP,
        "building_id": BUILDING_PROP,
        "start_date": {"type": "string", "description": "新的合同开始日期，格式 YYYY-MM-DD"},
        "end_date": {"type": "string", "description": "新的合同结束日期，格式 YYYY-MM-DD"},
        "monthly_rent": {"type": "number", "description": "新的月租金额"},
        "water_unit_price": {"type": "number", "description": "新的水费单价"},
        "electric_unit_price": {"type": "number", "description": "新的电费单价"},
        "deposit": {"type": "number", "description": "新的保证金金额"},
        "water_meter_id": {"type": "integer", "description": "新的水表 ID，必须属于合同房间"},
        "electric_meter_id": {"type": "integer", "description": "新的电表 ID，必须属于合同房间"},
        "other_fee_details": OTHER_FEE_DETAILS_PROP,
    }),
    _tool_schema("room_update_from_ai", "准备修改房间信息。可改房间号、楼层、户型或状态；返回待确认操作，不直接写库。", {
        "room_id": ROOM_ID_PROP,
        "room_number": ROOM_PROP,
        "building_id": BUILDING_PROP,
        "new_room_number": {"type": "string", "description": "新的房间号"},
        "room_type": {"type": "string", "description": "新的户型"},
        "floor": {"type": "integer", "description": "新的楼层"},
        "status": {"type": "string", "enum": ["idle", "rented", "闲置", "在租", "已租", "空置"], "description": "新的房间状态"},
    }),
    _tool_schema("meter_update_from_ai", "准备修改表具初始信息。可改表号或初始读数；返回待确认操作，不直接写库。", {
        "meter_id": METER_ID_PROP,
        "room_number": ROOM_PROP,
        "meter_type": METER_TYPE_PROP,
        "building_id": BUILDING_PROP,
        "meter_no": {"type": "string", "description": "新的表号"},
        "init_reading": {"type": "number", "description": "新的初始读数"},
    }),
    _tool_schema("contract_create_from_ai", "准备新建租房合同。可选择已有租户，也可根据租客姓名、手机号和证件号准备新租户；返回待确认操作，不直接写库。", {
        "tenant_id": {"type": "integer", "description": "已有租户 ID；如果要新建租户，不传 tenant_id，改传 tenant_name"},
        "tenant_name": TENANT_PROP,
        "tenant_phone": {"type": "string", "description": "新租户手机号，可选"},
        "tenant_id_card": {"type": "string", "description": "新租户证件号，可选"},
        "room_id": {"type": "integer", "description": "房间 ID；如果只知道房间号，可传 room_number"},
        "room_number": ROOM_PROP,
        "building_id": BUILDING_PROP,
        "building_name": {"type": "string", "description": "楼栋名称；用户说楼栋名称如石潭布时传这里"},
        "start_date": {"type": "string", "description": "合同开始日期，格式 YYYY-MM-DD"},
        "end_date": {"type": "string", "description": "合同结束日期，格式 YYYY-MM-DD，可为空"},
        "monthly_rent": {"type": "number", "description": "月租金额，必填"},
        "water_unit_price": {"type": "number", "description": "水费单价，默认 0"},
        "electric_unit_price": {"type": "number", "description": "电费单价，默认 0"},
        "deposit": {"type": "number", "description": "保证金金额，默认 0"},
        "water_meter_id": {"type": "integer", "description": "绑定水表 ID，可选，必须属于该房间"},
        "electric_meter_id": {"type": "integer", "description": "绑定电表 ID，可选，必须属于该房间"},
        "other_fee_details": OTHER_FEE_DETAILS_PROP,
    }, ["start_date", "monthly_rent"]),
    _tool_schema("payment_list_paid", "查询今日或本月已收款记录。", {"date_range": {"type": "string", "enum": ["today", "month"], "description": "today 查询今日，month 查询月份"}, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("payment_list_pending", "查询指定月份待收款列表。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("payment_check_anomalies", "检查指定月份收款异常。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("payment_compare_paid_amount", "对比某账单实收金额和应收金额差异。", {"bill_id": BILL_ID_PROP}, ["bill_id"]),
    _tool_schema("payment_confirm_from_ai", "准备确认某房间账单收款，返回待确认操作，不直接写库。未传金额时默认收取当前全部待收金额。", {
        "bill_id": BILL_ID_PROP,
        "room_number": ROOM_PROP,
        "month": MONTH_PROP,
        "building_id": BUILDING_PROP,
        "amount": {"type": "number", "description": "本次实收金额；不传则默认当前全部待收金额"},
        "pay_date": {"type": "string", "description": "收款日期，格式 YYYY-MM-DD；不传默认今天"},
        "pay_method": {"type": "string", "description": "收款方式，例如微信、支付宝、现金、银行转账，可选"},
        "remark": {"type": "string", "description": "收款备注，可选"},
    }),
]


_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "rent_plan_list_month_status": rent_plan_list_month_status,
    "rent_plan_list_uncreated_bills": rent_plan_list_uncreated_bills,
    "rent_plan_get_room_progress": rent_plan_get_room_progress,
    "rent_plan_check_anomalies": rent_plan_check_anomalies,
    "meter_reading_list_month_status": meter_reading_list_month_status,
    "meter_reading_get_room_reading": meter_reading_get_room_reading,
    "meter_reading_list_missing": meter_reading_list_missing,
    "meter_reading_check_anomalies": meter_reading_check_anomalies,
    "meter_reading_save_from_ai": meter_reading_save_from_ai,
    "confirm_save_meter_reading": confirm_save_meter_reading,
    "bill_explain_amount": bill_explain_amount,
    "bill_get_bill_detail": bill_get_bill_detail,
    "bill_generate_draft": bill_generate_draft,
    "bill_validate_preview": bill_validate_preview,
    "bill_get_receipt_image_data": bill_get_receipt_image_data,
    "bill_create_from_ai": bill_create_from_ai,
    "confirm_create_bill": confirm_create_bill,
    "contract_tenant_get_contract_detail": contract_tenant_get_contract_detail,
    "contract_tenant_list_active_contracts": contract_tenant_list_active_contracts,
    "contract_tenant_get_room_tenant": contract_tenant_get_room_tenant,
    "contract_tenant_get_contract_meter_binding": contract_tenant_get_contract_meter_binding,
    "contract_tenant_list_expiring_contracts": contract_tenant_list_expiring_contracts,
    "contract_tenant_list_empty_rooms": contract_tenant_list_empty_rooms,
    "contract_update_from_ai": contract_update_from_ai,
    "confirm_update_contract": confirm_update_contract,
    "room_update_from_ai": room_update_from_ai,
    "confirm_update_room": confirm_update_room,
    "meter_update_from_ai": meter_update_from_ai,
    "confirm_update_meter": confirm_update_meter,
    "contract_create_from_ai": contract_create_from_ai,
    "confirm_create_contract": confirm_create_contract,
    "payment_list_paid": payment_list_paid,
    "payment_list_pending": payment_list_pending,
    "payment_check_anomalies": payment_check_anomalies,
    "payment_compare_paid_amount": payment_compare_paid_amount,
    "payment_confirm_from_ai": payment_confirm_from_ai,
    "confirm_record_payment": confirm_record_payment,
}


def get_tool_schemas() -> List[Dict[str, Any]]:
    return TOOL_SCHEMAS


def execute_tool(name: str, args: Any = None) -> Dict[str, Any]:
    handler = _HANDLERS.get(name)
    if not handler:
        return {"ok": False, "tool": name, "error": "工具不在白名单内"}

    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except Exception:
            return {"ok": False, "tool": name, "error": "工具参数不是合法 JSON"}
    if not isinstance(args, dict):
        args = {}

    try:
        params = inspect.signature(handler).parameters
        filtered = {k: v for k, v in args.items() if k in params}
        return {"ok": True, "tool": name, "data": handler(**filtered)}
    except Exception as exc:
        return {"ok": False, "tool": name, "error": str(exc)}
