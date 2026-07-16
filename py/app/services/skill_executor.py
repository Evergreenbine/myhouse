# -*- coding: utf-8 -*-
"""业务 Skill 工具执行层。

查询能力直接执行；会改变业务数据的工具必须先返回待确认操作，再由用户确认执行。
"""
from __future__ import annotations

import inspect
import json
import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

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
            parsed = json.loads(value) if value.strip() else []
        except Exception:
            parsed = []
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
) -> Optional[Dict[str, Any]]:
    cid = _int_or_none(contract_id)
    if cid:
        contract = db.get_contract(cid)
        if contract and contract.get("status") == "active":
            return contract
        return None

    room_text = str(room_number or "").strip()
    contracts = db.get_contracts(True, _int_or_none(building_id)) or []
    if not room_text:
        return contracts[0] if len(contracts) == 1 else None

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
        if room_text in haystack:
            fuzzy.append(contract)
    return fuzzy[0] if fuzzy else None


def _bill_for_contract(contract_id: Any, month: str) -> Optional[Dict[str, Any]]:
    bills = db.get_bills(month, _int_or_none(contract_id)) or []
    return bills[0] if bills else None


def _rent_plan_row(contract: Dict[str, Any], month: str) -> Dict[str, Any]:
    bill = _bill_for_contract(contract.get("id"), month)
    if not bill:
        expected = _num(contract.get("monthly_rent"))
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
                "other_fee": 0.0,
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
        },
    }


def rent_plan_list_month_status(month: Any = None, building_id: Any = None) -> Dict[str, Any]:
    month = _normalize_month(month)
    contracts = db.get_contracts(True, _int_or_none(building_id)) or []
    rows = [_rent_plan_row(contract, month) for contract in contracts]
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
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
    month = _normalize_month(month)
    result = []
    for mtype in _meter_types(meter_type):
        rows = db.get_monthly_meter_readings(mtype, _int_or_none(building_id), month) or []
        normalized_rows = []
        for row in rows:
            normalized_rows.append({
                "meter_id": row.get("id"),
                "meter_type": mtype,
                "meter_type_label": METER_TYPE_LABELS.get(mtype, mtype),
                "building": row.get("building_name", ""),
                "room_number": row.get("room_number", ""),
                "meter_no": row.get("meter_no", ""),
                "month": month,
                "status": "recorded" if row.get("reading") is not None else "missing",
                "status_label": _status_label("recorded" if row.get("reading") is not None else "missing"),
                "reading": row.get("reading"),
                "previous_reading": row.get("previous_reading"),
                "usage": row.get("usage"),
                "has_photo": bool(row.get("photo")),
                "remark": row.get("remark", ""),
            })
        result.append({
            "meter_type": mtype,
            "meter_type_label": METER_TYPE_LABELS.get(mtype, mtype),
            "total": len(normalized_rows),
            "recorded": sum(1 for r in normalized_rows if r["status"] == "recorded"),
            "missing": sum(1 for r in normalized_rows if r["status"] == "missing"),
            "rows": normalized_rows,
        })
    return {"month": month, "items": result}


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
    return {"month": data["month"], "found": bool(matches), "rows": matches}


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
    total = round(rent + water_fee + electric_fee, 2)

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
            "other_fee": 0.0,
            "other_fee_details": [],
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
    overwrite: Any = False,
    rent_amount: Any = None,
    water_fee: Any = None,
    electric_fee: Any = None,
    other_fee: Any = None,
    other_fee_details: Any = None,
    water_curr: Any = None,
    electric_curr: Any = None,
    water_last: Any = None,
    electric_last: Any = None,
) -> Dict[str, Any]:
    month = _normalize_month(month)
    contract = _find_active_contract(room_number=room_number, contract_id=contract_id, building_id=building_id)
    if not contract:
        return {"success": False, "month": month, "message": "未找到有效合同，无法生成账单"}

    existing = _bill_for_contract(contract.get("id"), month)
    if existing and not _bool(overwrite):
        return {
            "success": False,
            "already_exists": True,
            "message": "该房间本月已经有账单，默认不重复生成。",
            "bill": existing,
            "receipt_image": _receipt_payload_from_bill(existing),
        }

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

    if other_fee_details is not None:
        normalized_other_fees = _normalize_other_fee_details(other_fee_details)
    elif other_fee is not None and other_fee != "":
        normalized_other_fees = _normalize_other_fee_details([], other_fee)
    elif existing and _bool(overwrite):
        normalized_other_fees = _normalize_other_fee_details(
            existing.get("other_fee_details"),
            existing.get("other_fee"),
        )
    else:
        normalized_other_fees = _normalize_other_fee_details(
            draft.get("other_fee_details"),
            draft.get("other_fee"),
        )
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

    receipt_image = _receipt_payload_from_draft(draft_payload)
    action_args = {
        "existing_bill_id": existing.get("id") if existing else None,
        "contract_id": contract.get("id"),
        "month": month,
        "overwrite": _bool(overwrite),
        "draft": draft,
    }
    overwrite_existing = bool(existing and _bool(overwrite))
    action = _pending_action(
        "create_bill",
        f"{'覆盖' if overwrite_existing else '保存'}{contract.get('room_number')} {month} 账单，合计 {_money(draft.get('total_amount'))}",
        "confirm_create_bill",
        action_args,
        {
            "room_number": contract.get("room_number"),
            "tenant_name": contract.get("tenant_name"),
            "month": month,
            "total_amount": _num(draft.get("total_amount")),
            "other_fee_details": normalized_other_fees,
            "overwrite": overwrite_existing,
        },
    )
    return {
        "success": True,
        "requires_confirmation": True,
        "action": "bill_prepared",
        "month": month,
        "draft": draft_payload,
        "pending_action": action,
        "receipt_image": receipt_image,
        "message": "账单草稿已准备，请用户确认后再保存。",
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
) -> tuple[Optional[Dict[str, Any]], str]:
    cid = _int_or_none(contract_id)
    if cid:
        contract = db.get_contract(cid)
        return (contract, "") if contract else (None, "未找到该合同")

    room_text = str(room_number or "").strip()
    if not room_text:
        return None, "请提供合同 ID，或说明楼栋和房间号"

    contracts = db.get_contracts(True, _int_or_none(building_id)) or []
    matches = [item for item in contracts if str(item.get("room_number") or "").strip() == room_text]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, "多个楼栋都有该房间号，请补充楼栋名称"
    return None, "未找到该房间的有效合同"


def _normalize_contract_date(value: Any, allow_empty: bool = False) -> tuple[Optional[str], str]:
    text = str(value or "").strip()
    if not text and allow_empty:
        return "", ""
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


def _contract_change_text(field: str, value: Any) -> str:
    if field in {"monthly_rent", "water_unit_price", "electric_unit_price", "deposit"}:
        return "¥" + _money(value)
    if field in {"water_meter_id", "electric_meter_id"}:
        return _meter_binding_text(value)
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

    if not changes:
        return None, "请说明要修改月租、水电单价、押金、合同日期或表具绑定中的哪一项"

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
    start_date: Any = _UNSET,
    end_date: Any = _UNSET,
    monthly_rent: Any = _UNSET,
    water_unit_price: Any = _UNSET,
    electric_unit_price: Any = _UNSET,
    deposit: Any = _UNSET,
    water_meter_id: Any = _UNSET,
    electric_meter_id: Any = _UNSET,
) -> Dict[str, Any]:
    contract, error = _resolve_contract_for_update(contract_id, room_number, building_id)
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


def contract_tenant_get_room_tenant(room_number: Any, building_id: Any = None) -> Dict[str, Any]:
    contract = _find_active_contract(room_number=room_number, building_id=building_id)
    if not contract:
        return {"found": False, "message": "该房间当前没有有效合同或未找到房间"}
    return {"found": True, "contract": contract}


def contract_tenant_get_contract_meter_binding(room_number: Any, building_id: Any = None) -> Dict[str, Any]:
    contract = _find_active_contract(room_number=room_number, building_id=building_id)
    if not contract:
        return {"found": False, "message": "该房间当前没有有效合同或未找到房间"}
    meters = db.get_meters(contract.get("room_id")) or []
    return {
        "found": True,
        "contract": contract,
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
BILL_ID_PROP = {"type": "integer", "description": "账单 ID"}
CONTRACT_ID_PROP = {"type": "integer", "description": "合同 ID"}
METER_TYPE_PROP = {"type": "string", "enum": ["water", "electric"], "description": "水表 water，电表 electric；不传表示全部"}

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
    _tool_schema("bill_create_from_ai", "AI助手根据已录入读数准备生成某房间某月账单，并返回账单图片数据。返回待确认操作，不直接写库。支持用户对话调整金额或读数。", {
        "room_number": ROOM_PROP,
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
        "water_curr": {"type": "number", "description": "用户指定的水表本月读数，可选"},
        "electric_curr": {"type": "number", "description": "用户指定的电表本月读数，可选"},
    }),
    _tool_schema("contract_tenant_get_room_tenant", "查询某房间当前租客和有效合同。", {"room_number": ROOM_PROP, "building_id": BUILDING_PROP}, ["room_number"]),
    _tool_schema("contract_tenant_get_contract_meter_binding", "查询某房间合同关联的水电表。", {"room_number": ROOM_PROP, "building_id": BUILDING_PROP}, ["room_number"]),
    _tool_schema("contract_tenant_list_expiring_contracts", "查询指定天数内即将到期的合同。", {"days": {"type": "integer", "description": "未来多少天内到期，默认 30"}, "building_id": BUILDING_PROP}),
    _tool_schema("contract_tenant_list_empty_rooms", "查询当前空置房间。", {"building_id": BUILDING_PROP}),
    _tool_schema("contract_update_from_ai", "准备修改现有合同。按合同 ID，或楼栋和房间定位合同；返回待确认操作，不直接写库。", {
        "contract_id": CONTRACT_ID_PROP,
        "room_number": ROOM_PROP,
        "building_id": BUILDING_PROP,
        "start_date": {"type": "string", "description": "新的合同开始日期，格式 YYYY-MM-DD"},
        "end_date": {"type": "string", "description": "新的合同结束日期，格式 YYYY-MM-DD"},
        "monthly_rent": {"type": "number", "description": "新的月租金额"},
        "water_unit_price": {"type": "number", "description": "新的水费单价"},
        "electric_unit_price": {"type": "number", "description": "新的电费单价"},
        "deposit": {"type": "number", "description": "新的保证金金额"},
        "water_meter_id": {"type": "integer", "description": "新的水表 ID，必须属于合同房间"},
        "electric_meter_id": {"type": "integer", "description": "新的电表 ID，必须属于合同房间"},
    }),
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
    "contract_tenant_get_room_tenant": contract_tenant_get_room_tenant,
    "contract_tenant_get_contract_meter_binding": contract_tenant_get_contract_meter_binding,
    "contract_tenant_list_expiring_contracts": contract_tenant_list_expiring_contracts,
    "contract_tenant_list_empty_rooms": contract_tenant_list_empty_rooms,
    "contract_update_from_ai": contract_update_from_ai,
    "confirm_update_contract": confirm_update_contract,
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
