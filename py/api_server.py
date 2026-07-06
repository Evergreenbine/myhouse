# -*- coding: utf-8 -*-
import json, os, sys, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, datetime, timedelta
from user_auth import load_user_config, save_user_config
from local_db import load_app_user, save_app_user, add_building, get_buildings, get_building, update_building, delete_building, add_room, get_rooms, get_room, add_tenant, get_tenants, get_tenant, update_tenant, set_tenant_status, add_contract, get_contracts, get_contract, end_contract, add_meter, get_meters, get_meter, add_reading, get_readings, get_latest_reading, add_bill, get_bills, get_bill, update_bill_status, add_payment, get_payments, delete_payment
PORT = 18520

class APIHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self._send_json({})

    def _get_empno(self):
        try:
            from local_db import load_app_user
            local = load_app_user()
            if local and local.get('empno'):
                return local.get('empno')
        except:
            pass
        try:
            cfg = load_user_config()
            return cfg.empno if cfg else ''
        except:
            return ''

    

    

    def do_GET(self):

        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path == "/api/status":
                return self._send_json({"status": "ok", "time": datetime.now().isoformat()})

            elif path == "/api/user/config":
                local = load_app_user()
                if local and local.get("empno"):
                    def _get(key, default=""):
                        return local.get(key, default)
                    bs = float(_get("base_salary", 30))
                    wm = int(_get("water_ml", 300))
                    we = _get("water_enabled", "True").lower() == "true"
                    ee = _get("eye_enabled", "True").lower() == "true"
                    return self._send_json({
                        "empno": _get("empno",""), "empname": _get("empname",""),
                        "car_plate": _get("car_plate",""), "base_salary": bs,
                        "avatar": _get("avatar_path","cat_icon.png"),
                        "water_enabled": we, "eye_enabled": ee, "water_ml": wm,
                        "api_key": _get("api_key",""), "openai_key": _get("openai_key",""),
                        "zhipu_key": _get("zhipu_key",""),
                        "custom_api_key": _get("custom_api_key",""),
                        "custom_base_url": _get("custom_base_url",""),
                        "custom_model": _get("custom_model",""),
                        "ai_provider": _get("ai_provider",""),
                        "ai_model": _get("ai_model","deepseek-v4-flash"),
                        "ai_persona": _get("ai_persona","warm"),
                        "ai_nickname": _get("ai_nickname","鍝堝熀绫?),
                        "user_nickname": _get("user_nickname","涓讳汉"),
                        "ai_avatar": _get("ai_avatar","cat_icon.png"),
                        "lunch_start": _get("lunch_start","12:05"),
                        "lunch_end": _get("lunch_end","13:05"),
                        "dinner_start": _get("dinner_start","17:30"),
                        "dinner_end": _get("dinner_end","18:00"),
                    })
                cfg = load_user_config()
                if cfg:
                    return self._send_json({
                        "empno": cfg.empno or "", "empname": cfg.empname or "",
                        "car_plate": cfg.car_plate or "", "base_salary": cfg.base_salary or 0,
                        "avatar": getattr(cfg,"avatar_path","cat_icon.png"),
                        "water_enabled": getattr(cfg,"water_enabled",True),
                        "eye_enabled": getattr(cfg,"eye_enabled",True),
                        "water_ml": getattr(cfg,"water_ml",300),
                        "api_key": getattr(cfg,"api_key",""),
                        "openai_key": getattr(cfg,"openai_key",""),
                        "zhipu_key": getattr(cfg,"zhipu_key",""),
                        "custom_api_key": getattr(cfg,"custom_api_key",""),
                        "custom_base_url": getattr(cfg,"custom_base_url",""),
                        "custom_model": getattr(cfg,"custom_model",""),
                        "ai_provider": getattr(cfg,"ai_provider",""),
                        "ai_model": getattr(cfg,"ai_model","deepseek-v4-flash"),
                        "ai_persona": getattr(cfg,"ai_persona","warm"),
                        "lunch_start": getattr(cfg,"lunch_start","12:05"),
                        "lunch_end": getattr(cfg,"lunch_end","13:05"),
                        "dinner_start": getattr(cfg,"dinner_start","17:30"),
                        "dinner_end": getattr(cfg,"dinner_end","18:00"),
                    })
                return self._send_json({"error":"not configured"}, 404)

            elif path == "/api/chat/list":
                from local_db import load_chats
                return self._send_json(load_chats())
            elif path == "/api/quote":
                import random
                qs_list = ["浠婂ぉ涔熸槸鍏冩皵婊℃弧鐨勪竴澶╋紒", "鍠濆彛姘翠紤鎭竴涓嬪惂~", "鎽搁奔涔熸槸鐢熶骇鍔涳紒"]
                return self._send_json({"quote": random.choice(qs_list)})

            elif path == "/api/weather":
                return self._send_json({"weather": "鈽€锔?鏅?28掳C"})

            elif path == "/api/ot-reason":
                ds = qs.get("date", [date.today().isoformat()])[0]
                r = get_reason(ds)
                return self._send_json({"reason": r, "date": ds})

            elif path == "/api/ot-reasons-bulk":
                return self._handle_ot_reasons_bulk(qs)

            elif path == "/api/user/status":
                cfg = load_user_config()
                if cfg and cfg.is_logged_in:
                    return self._send_json({"logged_in": True, "empno": cfg.empno, "empname": cfg.empname})
                return self._send_json({"logged_in": False})


            elif path == "/api/rental":
                import json
                body = {}
                cl = self.rfile.read(int(self.headers.get("Content-Length",0)))
                if cl: body = json.loads(cl.decode("utf-8"))
                table = body.get("table","")
                action = body.get("action","")
                data = body.get("data",{})
                result = None
                if table=="buildings":
                    if action=="list": result = get_buildings()
                    elif action=="get": result = get_building(data.get("id"))
                    elif action=="add": result = add_building(data.get("name",""), data.get("address",""))
                    elif action=="update": update_building(data.get("id"),data.get("name",""),data.get("address",""));result={"success":True}
                    elif action=="delete": delete_building(data.get("id"));result={"success":True}
                elif table=="rooms":
                    if action=="list": result = get_rooms(data.get("building_id"))
                    elif action=="get": result = get_room(data.get("id"))
                    elif action=="add": result = add_room(data.get("building_id"),data.get("room_number",""))
                elif table=="tenants":
                    if action=="list": result = get_tenants(data.get("active_only",True))
                    elif action=="get": result = get_tenant(data.get("id"))
                    elif action=="add": result = add_tenant(data.get("name",""),data.get("phone",""),data.get("id_card",""))
                    elif action=="update": update_tenant(data.get("id"),data.get("name",""),data.get("phone",""),data.get("id_card",""));result={"success":True}
                    elif action=="set_status": set_tenant_status(data.get("id"),data.get("status","active"));result={"success":True}
                elif table=="contracts":
                    if action=="list": result = get_contracts(data.get("active_only",True))
                    elif action=="get": result = get_contract(data.get("id"))
                    elif action=="add": result = add_contract(data.get("tenant_id"),data.get("room_id"),data.get("start_date",""),data.get("end_date",""),data.get("monthly_rent",0),data.get("water_price",0),data.get("electric_price",0),data.get("deposit",0),data.get("contract_file",""),data.get("status","active"))
                    elif action=="end": end_contract(data.get("id"));result={"success":True}
                elif table=="meters":
                    if action=="list": result = get_meters(data.get("room_id"))
                    elif action=="get": result = get_meter(data.get("id"))
                    elif action=="add": result = add_meter(data.get("room_id"),data.get("type","water"),data.get("meter_no",""),data.get("init_reading",0))
                elif table=="readings":
                    if action=="list": result = get_readings(data.get("meter_id"),data.get("limit",50))
                    elif action=="add": result = add_reading(data.get("meter_id"),data.get("reading_date",""),data.get("reading",0),data.get("photo",""),data.get("remark",""))
                    elif action=="latest": result = get_latest_reading(data.get("meter_id"))
                elif table=="bills":
                    if action=="list": result = get_bills(data.get("month"),data.get("contract_id"))
                    elif action=="get": result = get_bill(data.get("id"))
                    elif action=="add": result = add_bill(data.get("contract_id"),data.get("billing_month",""),data.get("rent_amount",0),data.get("water_fee",0),data.get("electric_fee",0),data.get("other_fee",0),data.get("remark",""))
                    elif action=="update_status": update_bill_status(data.get("id"),data.get("status","unpaid"));result={"success":True}
                elif table=="payments":
                    if action=="list": result = get_payments(data.get("bill_id"))
                    elif action=="add": result = add_payment(data.get("bill_id"),data.get("amount",0),data.get("pay_date"),data.get("pay_method",""),data.get("remark",""))
                    elif action=="delete": delete_payment(data.get("id"));result={"success":True}
                if result is None: result = {"error":"unknown table or action"}
                return self._send_json(result)

        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e)}, 500)
def run():
    HTTPServer(("0.0.0.0", PORT), APIHandler).serve_forever()

if __name__ == "__main__":
    run()
