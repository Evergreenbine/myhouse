# -*- coding: utf-8 -*-
"""业务 Skill 工具执行层。

第一版只开放查询、解释、检查和草稿生成能力；所有会改变业务数据的动作都不在白名单内。
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

    if row.get("reading_id") and not _bool(overwrite):
        return {
            "success": False,
            "requires_confirmation": True,
            "message": "该月份已经有读数，默认不覆盖；如需覆盖请明确说明。",
            "existing": _public_meter_row(row),
        }

    action_args = {
        "meter_id": row.get("id"),
        "room_number": row.get("room_number"),
        "meter_type": mtype,
        "month": month,
        "reading": value,
        "photo": str(photo or ""),
        "remark": str(remark or "AI助手录入"),
    }
    action = _pending_action(
        "save_meter_reading",
        f"录入{row.get('room_number')} {month} {METER_TYPE_LABELS.get(mtype, mtype)}读数 {value}",
        "confirm_save_meter_reading",
        action_args,
        {
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
        latest = _find_meter_row_for_room(room_number, str(meter_type), month)
    return {
        "success": True,
        "action": "meter_reading_saved",
        "month": month,
        "meter_id": mid,
        "room_number": room_number,
        "meter_type": meter_type,
        "reading": value,
        "photo_saved": bool(photo),
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
    return {
        "image_type": "bill_receipt",
        "source": "saved_bill",
        "bill_id": bill.get("id"),
        "file_name": f"bill_{month}_{room_number}.png",
        "receipt": {
            "title": "房租、水、电费（专用）收据",
            "no": f"{str(month).replace('-', '')}{room_number}",
            "month": month,
            "room_number": room_number,
            "tenant_name": bill.get("tenant_name") or contract.get("tenant_name", ""),
            "collector": "吴钦腾",
            "issue_date": date.today().isoformat(),
            "items": [
                _receipt_item(
                    "水费",
                    bill.get("water_current_reading"),
                    bill.get("water_last_reading"),
                    contract.get("water_unit_price"),
                    bill.get("water_fee"),
                    1,
                ),
                _receipt_item(
                    "电费",
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
    return {
        "image_type": "bill_receipt",
        "source": "draft",
        "bill_id": None,
        "file_name": f"bill_draft_{month}_{room_number}.png",
        "receipt": {
            "title": "房租、水、电费（专用）收据",
            "no": f"{str(month).replace('-', '')}{room_number}",
            "month": month,
            "room_number": room_number,
            "tenant_name": contract.get("tenant_name", ""),
            "collector": "吴钦腾",
            "issue_date": date.today().isoformat(),
            "items": [
                _receipt_item(
                    "水费",
                    draft.get("water_curr"),
                    draft.get("water_last"),
                    contract.get("water_unit_price"),
                    draft.get("water_fee"),
                    1,
                ),
                _receipt_item(
                    "电费",
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
        "other_fee": other_fee,
        "water_curr": water_curr,
        "electric_curr": electric_curr,
        "water_last": water_last,
        "electric_last": electric_last,
    }.items():
        if value is not None and value != "":
            draft[key] = _num(value)
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
    action = _pending_action(
        "create_bill",
        f"保存{contract.get('room_number')} {month} 账单，合计 {_money(draft.get('total_amount'))}",
        "confirm_create_bill",
        action_args,
        {
            "room_number": contract.get("room_number"),
            "tenant_name": contract.get("tenant_name"),
            "month": month,
            "total_amount": _num(draft.get("total_amount")),
            "overwrite": bool(existing),
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
    if existing_id and _bool(overwrite):
        db.update_bill(
            existing_id,
            contract_id,
            month,
            _num(draft.get("rent_amount")),
            _num(draft.get("water_fee")),
            _num(draft.get("electric_fee")),
            _num(draft.get("other_fee")),
            "AI助手确认更新账单",
            draft.get("water_last"),
            draft.get("water_curr"),
            draft.get("electric_last"),
            draft.get("electric_curr"),
            draft.get("water_photo"),
            draft.get("electric_photo"),
        )
        bill_id = existing_id
    else:
        bill_id = db.add_bill(
            contract_id,
            month,
            _num(draft.get("rent_amount")),
            _num(draft.get("water_fee")),
            _num(draft.get("electric_fee")),
            _num(draft.get("other_fee")),
            "AI助手确认生成账单",
            draft.get("water_last") or 0,
            draft.get("water_curr"),
            draft.get("electric_last") or 0,
            draft.get("electric_curr"),
            draft.get("water_photo") or "",
            draft.get("electric_photo") or "",
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
        "other_fee": {"type": "number", "description": "用户指定的其他费用，可选"},
        "water_curr": {"type": "number", "description": "用户指定的水表本月读数，可选"},
        "electric_curr": {"type": "number", "description": "用户指定的电表本月读数，可选"},
    }),
    _tool_schema("contract_tenant_get_room_tenant", "查询某房间当前租客和有效合同。", {"room_number": ROOM_PROP, "building_id": BUILDING_PROP}, ["room_number"]),
    _tool_schema("contract_tenant_get_contract_meter_binding", "查询某房间合同关联的水电表。", {"room_number": ROOM_PROP, "building_id": BUILDING_PROP}, ["room_number"]),
    _tool_schema("contract_tenant_list_expiring_contracts", "查询指定天数内即将到期的合同。", {"days": {"type": "integer", "description": "未来多少天内到期，默认 30"}, "building_id": BUILDING_PROP}),
    _tool_schema("contract_tenant_list_empty_rooms", "查询当前空置房间。", {"building_id": BUILDING_PROP}),
    _tool_schema("payment_list_paid", "查询今日或本月已收款记录。", {"date_range": {"type": "string", "enum": ["today", "month"], "description": "today 查询今日，month 查询月份"}, "month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("payment_list_pending", "查询指定月份待收款列表。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("payment_check_anomalies", "检查指定月份收款异常。", {"month": MONTH_PROP, "building_id": BUILDING_PROP}),
    _tool_schema("payment_compare_paid_amount", "对比某账单实收金额和应收金额差异。", {"bill_id": BILL_ID_PROP}, ["bill_id"]),
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
    "payment_list_paid": payment_list_paid,
    "payment_list_pending": payment_list_pending,
    "payment_check_anomalies": payment_check_anomalies,
    "payment_compare_paid_amount": payment_compare_paid_amount,
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
