import local_db as db
from ai_service import ai_svc

from app.services import ai_chat


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
        "water_price": data.get("water_price", existing.get("water_unit_price", 0)),
        "electric_price": data.get("electric_price", existing.get("electric_unit_price", 0)),
        "deposit": data.get("deposit", existing.get("deposit", 0)),
        "contract_file": data.get("contract_file", existing.get("contract_file", "")),
        "status": data.get("status", existing.get("status", "active")),
        "water_meter_id": data.get("water_meter_id", existing.get("water_meter_id")),
        "electric_meter_id": data.get("electric_meter_id", existing.get("electric_meter_id")),
    }


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
            return db.add_room(data.get("building_id"), data.get("room_number", ""), data.get("floor", 1), data.get("status", "idle"))
        if action == "update":
            db.update_room(data.get("id"), data.get("building_id"), data.get("room_number", ""), data.get("floor", 1), data.get("status", "idle"))
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
            return db.add_contract(
                data.get("tenant_id"),
                data.get("room_id"),
                data.get("start_date", ""),
                data.get("end_date", ""),
                data.get("monthly_rent", 0),
                data.get("water_price", 0),
                data.get("electric_price", 0),
                data.get("deposit", 0),
                data.get("contract_file", ""),
                data.get("status", "active"),
                data.get("water_meter_id"),
                data.get("electric_meter_id"),
            )
        if action == "update":
            payload = _contract_payload(data)
            if not payload:
                return {"error": "contract not found"}
            db.update_contract(data.get("id"), **payload)
            return {"success": True}
        if action == "end":
            db.end_contract(data.get("id"))
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
            return db.get_monthly_meter_readings(data.get("type", "water"), data.get("building_id"), data.get("month", ""))
        if action == "save_monthly":
            return db.save_monthly_meter_reading(data.get("meter_id"), data.get("month", ""), data.get("reading", 0), data.get("photo", ""), data.get("remark", ""))
        if action == "overview":
            return db.get_meter_reading_overview(data.get("type", "water"), data.get("building_id"), data.get("start_month", "2026-06"), data.get("end_month", ""))

    if table == "bills":
        if action == "list":
            return db.get_bills(data.get("month"), data.get("contract_id"))
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
            )
            return {"success": True}
        if action == "update_status":
            db.update_bill_status(data.get("id"), data.get("status", "unpaid"))
            return {"success": True}

    if table == "payments":
        if action == "list":
            return db.get_payments(data.get("bill_id"))
        if action == "add":
            return db.add_payment(data.get("bill_id"), data.get("amount", 0), data.get("pay_date"), data.get("pay_method", ""), data.get("remark", ""))
        if action == "delete":
            db.delete_payment(data.get("id"))
            return {"success": True}

    if table == "_ai":
        if action == "chat":
            return ai_chat.chat(data)
        if action == "save_chat":
            return ai_chat.save_chat(data)
        if action == "list_chats":
            return ai_chat.list_chats()
        if action == "delete_chat":
            return ai_chat.delete_chat(data)
        if action == "init_knowledge":
            return ai_chat.init_knowledge()

    if table == "_ocr":
        if action == "read":
            image = data.get("image", "")
            meter_type = data.get("meter_type", "电表")
            num, err = ai_svc.read_meter_image(image, meter_type)
            if num is not None:
                return {"numbers": [num], "source": "ai"}
            return {"numbers": [], "source": "ai", "error": err or "AI识别失败"}

    return {"error": "unknown table or action"}

