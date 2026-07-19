import local_db as db
import json
from ai_service import ai_svc

from app.services import ai_chat


def _json_text(value, default="[]"):
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _contract_payload(data):
    existing = db.get_contract(data.get("id")) or {}
    if data.get("id") and not existing:
        return None
    return {
        "tenant_id": data.get("tenant_id", existing.get("tenant_id")),
        "room_id": data.get("room_id", existing.get("room_id")),
        "start_date": data.get("start_date", existing.get("start_date", "")),
        "end_date": data.get("end_date", existing.get("end_date", "")),
        "monthly_rent": data.get("monthly_rent", existing.get("monthly_rent", 0)),
        "water_price": data.get("water_unit_price", data.get("water_price", existing.get("water_unit_price", 0))),
        "electric_price": data.get("electric_unit_price", data.get("electric_price", existing.get("electric_unit_price", 0))),
        "deposit": data.get("deposit", existing.get("deposit", 0)),
        "contract_file": data.get("contract_file", existing.get("contract_file", "")),
        "status": data.get("status", existing.get("status", "active")),
        "water_meter_id": data.get("water_meter_id", existing.get("water_meter_id")),
        "electric_meter_id": data.get("electric_meter_id", existing.get("electric_meter_id")),
        "other_fee_details": _json_text(data.get("other_fee_details", existing.get("other_fee_details", "[]"))),
    }


def _normalize_meter_text(value):
    return "".join(str(value or "").strip().lower().split()).replace("-", "")


def _enrich_meter_analysis(analysis, meter_type_hint=""):
    result = dict(analysis or {})
    normalized_type = str(result.get("meter_type") or "unknown")
    if normalized_type == "unknown":
        hint = str(meter_type_hint or "").lower()
        if "水" in hint or "water" in hint:
            normalized_type = "water"
        elif "电" in hint or "electric" in hint:
            normalized_type = "electric"
    result["meter_type"] = normalized_type

    rows = db.get_meters(mtype=normalized_type if normalized_type in {"water", "electric"} else None) or []
    meter_number = _normalize_meter_text(result.get("meter_number"))
    room_number = _normalize_meter_text(result.get("room_number"))
    building_name = _normalize_meter_text(result.get("building_name"))

    exact_meter = [row for row in rows if meter_number and _normalize_meter_text(row.get("meter_no")) == meter_number]
    matches = exact_meter
    if not matches and room_number:
        matches = [row for row in rows if _normalize_meter_text(row.get("room_number")) == room_number]
    if building_name and matches:
        scoped = [
            row for row in matches
            if building_name in _normalize_meter_text(row.get("building_name"))
            or _normalize_meter_text(row.get("building_name")) in building_name
        ]
        if scoped:
            matches = scoped

    if len(matches) == 1:
        row = matches[0]
        result.update({
            "meter_id": row.get("id"),
            "meter_type": row.get("type") or normalized_type,
            "meter_number": row.get("meter_no") or result.get("meter_number"),
            "room_id": row.get("room_id"),
            "room_number": row.get("room_number") or result.get("room_number"),
            "building_id": row.get("building_id"),
            "building_name": row.get("building_name") or result.get("building_name"),
            "match_status": "matched",
            "match_source": "meter_number" if exact_meter else "room_number",
        })
        contracts = db.get_contracts(True, row.get("building_id")) or []
        contract = next((item for item in contracts if item.get("room_id") == row.get("room_id")), None)
        if contract:
            result.update({
                "contract_id": contract.get("id"),
                "tenant_id": contract.get("tenant_id"),
                "tenant_name": contract.get("tenant_name"),
            })
    else:
        result["match_status"] = "ambiguous" if len(matches) > 1 else "unmatched"

    candidates = []
    for row in matches[:12]:
        contracts = db.get_contracts(True, row.get("building_id")) or []
        contract = next((item for item in contracts if item.get("room_id") == row.get("room_id")), None)
        candidates.append({
            "meter_id": row.get("id"),
            "meter_number": row.get("meter_no"),
            "meter_type": row.get("type"),
            "building_id": row.get("building_id"),
            "building_name": row.get("building_name"),
            "room_id": row.get("room_id"),
            "room_number": row.get("room_number"),
            "tenant_id": contract.get("tenant_id") if contract else None,
            "tenant_name": contract.get("tenant_name") if contract else None,
        })
    result["candidates"] = candidates
    return result


def dispatch(table, action, data):
    data = data or {}

    if table == "buildings":
        if action == "list":
            return db.get_buildings()
        if action == "get":
            return db.get_building(data.get("id"))
        if action == "add":
            return db.add_building(data.get("name", ""), data.get("address", ""))
        if action == "update":
            db.update_building(data.get("id"), data.get("name", ""), data.get("address", ""))
            return {"success": True}

    if table == "rooms":
        if action == "list":
            return db.get_rooms(data.get("building_id"))
        if action == "get":
            return db.get_room(data.get("id"))
        if action == "add":
            return db.add_room(data.get("building_id"), data.get("room_number", ""), data.get("floor", 1), data.get("status", "idle"), data.get("room_type", "单间"))
        if action == "update":
            db.update_room(data.get("id"), data.get("building_id"), data.get("room_number", ""), data.get("floor", 1), data.get("status", "idle"), data.get("room_type", "单间"))
            return {"success": True}

    if table == "tenants":
        if action == "list":
            return db.get_tenants(data.get("active_only", True), data.get("building_id"))
        if action == "get":
            return db.get_tenant(data.get("id"))
        if action == "add":
            return db.add_tenant(data.get("name", ""), data.get("phone", ""), data.get("id_card", ""), data.get("status", "active"), data.get("building_id"), data.get("room_id"))
        if action == "update":
            db.update_tenant(data.get("id"), data.get("name", ""), data.get("phone", ""), data.get("id_card", ""), data.get("status", "active"), data.get("building_id"), data.get("room_id"))
            return {"success": True}
        if action == "set_status":
            db.set_tenant_status(data.get("id"), data.get("status", "active"))
            return {"success": True}

    if table == "contracts":
        if action == "list":
            return db.get_contracts(data.get("active_only", True), data.get("building_id"))
        if action == "get":
            return db.get_contract(data.get("id"))
        if action == "add":
            tenant_id = data.get("tenant_id")
            room_id = data.get("room_id")
            if not tenant_id and str(data.get("tenant_name") or "").strip():
                room = db.get_room(room_id) or {}
                tenant_id = db.add_tenant(
                    str(data.get("tenant_name") or "").strip(),
                    str(data.get("tenant_phone") or "").strip(),
                    str(data.get("tenant_id_card") or "").strip(),
                    "active",
                    room.get("building_id") or data.get("building_id"),
                    str(room_id) if room_id not in {None, ""} else None,
                )
            if not tenant_id:
                return {"error": "tenant is required"}
            return db.add_contract(
                tenant_id,
                room_id,
                data.get("start_date", ""),
                data.get("end_date", ""),
                data.get("monthly_rent", 0),
                data.get("water_unit_price", data.get("water_price", 0)),
                data.get("electric_unit_price", data.get("electric_price", 0)),
                data.get("deposit", 0),
                data.get("contract_file", ""),
                data.get("status", "active"),
                data.get("water_meter_id"),
                data.get("electric_meter_id"),
                _json_text(data.get("other_fee_details", "[]")),
            )
        if action == "update":
            payload = _contract_payload(data)
            if not payload:
                return {"error": "contract not found"}
            db.update_contract(data.get("id"), **payload)
            return {"success": True}
        if action == "end":
            db.end_contract(data.get("id"), data.get("end_date", ""))
            return {"success": True}

    if table == "meters":
        if action == "list":
            return db.get_meters(data.get("room_id"), data.get("building_id"), data.get("type"))
        if action == "get":
            return db.get_meter(data.get("id"))
        if action == "add":
            return db.add_meter(data.get("room_id"), data.get("type", "water"), data.get("meter_no", ""), data.get("init_reading", 0), data.get("photo", ""))
        if action == "update":
            db.update_meter(data.get("id"), data.get("room_id"), data.get("type", "water"), data.get("meter_no", ""), data.get("init_reading", 0), data.get("photo"))
            return {"success": True}

    if table == "readings":
        if action == "list":
            return db.get_readings(data.get("meter_id"), data.get("limit", 50))
        if action == "add":
            return db.add_reading(data.get("meter_id"), data.get("reading_date", ""), data.get("reading", 0), data.get("photo", ""), data.get("remark", ""))
        if action == "latest":
            return db.get_latest_reading(data.get("meter_id"))
        if action == "monthly":
            return db.get_monthly_meter_readings(data.get("type", "water"), data.get("building_id"), data.get("month", ""), data.get("meter_id"))
        if action == "save_monthly":
            return db.save_monthly_meter_reading(data.get("meter_id"), data.get("month", ""), data.get("reading", 0), data.get("photo", ""), data.get("remark", ""))
        if action == "overview":
            return db.get_meter_reading_overview(data.get("type", "water"), data.get("building_id"), data.get("start_month", "2026-06"), data.get("end_month", ""))

    if table == "bills":
        if action == "list":
            return db.get_bills(data.get("month"), data.get("contract_id"), data.get("include_photos", False))
        if action == "get":
            return db.get_bill(data.get("id"))
        if action == "add":
            return db.add_bill(
                data.get("contract_id"),
                data.get("billing_month", ""),
                data.get("rent_amount", 0),
                data.get("water_fee", 0),
                data.get("electric_fee", 0),
                data.get("other_fee", 0),
                data.get("remark", ""),
                data.get("water_last", 0),
                data.get("water_curr", 0),
                data.get("electric_last", 0),
                data.get("electric_curr", 0),
                data.get("water_photo", ""),
                data.get("electric_photo", ""),
                data.get("other_fee_details", "[]"),
            )
        if action == "update":
            db.update_bill(
                data.get("id"),
                data.get("contract_id"),
                data.get("billing_month"),
                data.get("rent_amount"),
                data.get("water_fee"),
                data.get("electric_fee"),
                data.get("other_fee"),
                data.get("remark"),
                data.get("water_last"),
                data.get("water_curr"),
                data.get("electric_last"),
                data.get("electric_curr"),
                data.get("water_photo"),
                data.get("electric_photo"),
                data.get("other_fee_details"),
            )
            return {"success": True}
        if action == "update_status":
            db.update_bill_status(data.get("id"), data.get("status", "unpaid"))
            return {"success": True}

    if table == "payments":
        if action == "list":
            return db.get_payments(
                data.get("bill_id"),
                data.get("month"),
                data.get("building_id"),
                data.get("keyword", ""),
                data.get("start_date"),
                data.get("end_date"),
                data.get("pay_method"),
            )
        if action == "add":
            return db.add_payment(data.get("bill_id"), data.get("amount", 0), data.get("pay_date"), data.get("pay_method", ""), data.get("remark", ""))
        if action == "update":
            return db.update_payment(data.get("id"), data.get("amount"), data.get("pay_date"), data.get("pay_method"), data.get("remark"))
        if action == "delete":
            db.delete_payment(data.get("id"))
            return {"success": True}

    if table == "_ai":
        if action == "chat":
            return ai_chat.chat(data)
        if action == "save_chat":
            return ai_chat.save_chat(data)
        if action == "list_chats":
            return ai_chat.list_chats(data)
        if action == "delete_chat":
            return ai_chat.delete_chat(data)
        if action == "archive_chat":
            return ai_chat.archive_chat(data)
        if action == "restore_chat":
            return ai_chat.restore_chat(data)
        if action == "init_knowledge":
            return ai_chat.init_knowledge()

    if table == "_ocr":
        if action == "analyze":
            image = data.get("image", "")
            meter_type = data.get("meter_type", "")
            analysis, err = ai_svc.analyze_meter_image(image, meter_type)
            if err:
                return {"success": False, "error": err}
            return {"success": True, **_enrich_meter_analysis(analysis, meter_type)}
        if action == "read":
            image = data.get("image", "")
            meter_type = data.get("meter_type", "电表")
            num, err = ai_svc.read_meter_image(image, meter_type)
            if num is not None:
                return {"numbers": [num], "source": "ai"}
            return {"numbers": [], "source": "ai", "error": err or "AI识别失败"}

    return {"error": "unknown table or action"}
