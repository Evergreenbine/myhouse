# -*- coding: utf-8 -*-
import json, os, sys, traceback, base64, tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, datetime, timedelta
from user_auth import load_user_config, save_user_config
from local_db import init as init_db, load_app_user, save_app_user, add_building, get_buildings, get_building, update_building, add_room, get_rooms, get_room, update_room, add_tenant, get_tenants, get_tenant, update_tenant, set_tenant_status, add_contract, get_contracts, get_contract, update_contract, end_contract, add_meter, get_meters, get_meter, update_meter, add_reading, get_readings, get_latest_reading, get_monthly_meter_readings, save_monthly_meter_reading, get_meter_reading_overview, add_bill, get_bills, get_bill, update_bill, update_bill_status, add_payment, get_payments, delete_payment
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

    def do_POST(self):
        return self.do_GET()

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

            elif path == "/api/user/config" and self.command == "GET":
                local = load_app_user()
                if local:
                    def _get(key, default=""):
                        return local.get(key, default)
                    return self._send_json({
                        "api_key": _get("api_key",""), "openai_key": _get("openai_key",""),
                        "zhipu_key": _get("zhipu_key",""), "qwen_key": _get("qwen_key",""),
                        "custom_api_key": _get("custom_api_key",""),
                        "custom_base_url": _get("custom_base_url",""),
                        "custom_model": _get("custom_model",""),
                        "ai_provider": _get("ai_provider",""),
                        "ai_model": _get("ai_model","deepseek-v4-flash"),
                        "ocr_provider": _get("ocr_provider","qwen"),
                        "ocr_model": _get("ocr_model","qwen-vl-max"),
                        "ocr_key": _get("ocr_key",""),
                        "ai_persona": _get("ai_persona","warm"),
                        "ai_nickname": _get("ai_nickname","哈基米"),
                        "user_nickname": _get("user_nickname","主人"),
                        "ai_avatar": _get("ai_avatar","cat_icon.png"),
                    })
                return self._send_json({})

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


            elif path == "/api/user/config" and self.command == "POST":
                import json
                body = {}
                cl = self.rfile.read(int(self.headers.get("Content-Length",0)))
                if cl: body = json.loads(cl.decode("utf-8"))
                save_app_user(body)
                return self._send_json({"success":True})

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
                elif table=="rooms":
                    if action=="list": result = get_rooms(data.get("building_id"))
                    elif action=="get": result = get_room(data.get("id"))
                    elif action=="add": result = add_room(data.get("building_id"),data.get("room_number",""),data.get("floor",1),data.get("status","idle"))
                    elif action=="update": update_room(data.get("id"),data.get("building_id"),data.get("room_number",""),data.get("floor",1),data.get("status","idle"));result={"success":True}
                elif table=="tenants":
                    if action=="list": result = get_tenants(data.get("active_only",True),data.get("building_id"))
                    elif action=="get": result = get_tenant(data.get("id"))
                    elif action=="add": result = add_tenant(data.get("name",""),data.get("phone",""),data.get("id_card",""),data.get("status","active"),data.get("building_id"),data.get("room_id"))
                    elif action=="update": update_tenant(data.get("id"),data.get("name",""),data.get("phone",""),data.get("id_card",""),data.get("status","active"),data.get("building_id"),data.get("room_id"));result={"success":True}
                    elif action=="set_status": set_tenant_status(data.get("id"),data.get("status","active"));result={"success":True}
                elif table=="contracts":
                    if action=="list": result = get_contracts(data.get("active_only",True),data.get("building_id"))
                    elif action=="get": result = get_contract(data.get("id"))
                    elif action=="add": result = add_contract(data.get("tenant_id"),data.get("room_id"),data.get("start_date",""),data.get("end_date",""),data.get("monthly_rent",0),data.get("water_price",0),data.get("electric_price",0),data.get("deposit",0),data.get("contract_file",""),data.get("status","active"),data.get("water_meter_id"),data.get("electric_meter_id"))
                    elif action=="update": update_contract(data.get("id"),data.get("tenant_id"),data.get("room_id"),data.get("start_date",""),data.get("end_date",""),data.get("monthly_rent",0),data.get("water_price",0),data.get("electric_price",0),data.get("deposit",0),data.get("contract_file",""),data.get("status","active"),data.get("water_meter_id"),data.get("electric_meter_id"));result={"success":True}
                    elif action=="end": end_contract(data.get("id"));result={"success":True}
                elif table=="meters":
                    if action=="list": result = get_meters(data.get("room_id"),data.get("building_id"),data.get("type"))
                    elif action=="get": result = get_meter(data.get("id"))
                    elif action=="add": result = add_meter(data.get("room_id"),data.get("type","water"),data.get("meter_no",""),data.get("init_reading",0))
                    elif action=="update": update_meter(data.get("id"),data.get("room_id"),data.get("type","water"),data.get("meter_no",""),data.get("init_reading",0));result={"success":True}
                elif table=="readings":
                    if action=="list": result = get_readings(data.get("meter_id"),data.get("limit",50))
                    elif action=="add": result = add_reading(data.get("meter_id"),data.get("reading_date",""),data.get("reading",0),data.get("photo",""),data.get("remark",""))
                    elif action=="latest": result = get_latest_reading(data.get("meter_id"))
                    elif action=="monthly": result = get_monthly_meter_readings(data.get("type","water"),data.get("building_id"),data.get("month",""))
                    elif action=="save_monthly": result = save_monthly_meter_reading(data.get("meter_id"),data.get("month",""),data.get("reading",0),data.get("photo",""),data.get("remark",""))
                    elif action=="overview": result = get_meter_reading_overview(data.get("type","water"),data.get("building_id"),data.get("start_month","2026-06"),data.get("end_month",""))
                elif table=="bills":
                    if action=="list": result = get_bills(data.get("month"),data.get("contract_id"))
                    elif action=="get": result = get_bill(data.get("id"))
                    elif action=="add": result = add_bill(data.get("contract_id"),data.get("billing_month",""),data.get("rent_amount",0),data.get("water_fee",0),data.get("electric_fee",0),data.get("other_fee",0),data.get("remark",""),data.get("water_last",0),data.get("water_curr",0),data.get("electric_last",0),data.get("electric_curr",0),data.get("water_photo",""),data.get("electric_photo",""))
                    elif action=="update": update_bill(data.get("id"),data.get("contract_id"),data.get("billing_month"),data.get("rent_amount"),data.get("water_fee"),data.get("electric_fee"),data.get("other_fee"),data.get("remark"),data.get("water_last"),data.get("water_curr"),data.get("electric_last"),data.get("electric_curr"),data.get("water_photo"),data.get("electric_photo"));result={"success":True}
                    elif action=="update_status": update_bill_status(data.get("id"),data.get("status","unpaid"));result={"success":True}
                elif table=="payments":
                    if action=="list": result = get_payments(data.get("bill_id"))
                    elif action=="add": result = add_payment(data.get("bill_id"),data.get("amount",0),data.get("pay_date"),data.get("pay_method",""),data.get("remark",""))
                    elif action=="delete": delete_payment(data.get("id"));result={"success":True}
                elif table=="_ai":
                    if action=="chat":
                        # 测试连通性：真正发送一条消息给AI，检查是否返回有效回复
                        if data.get("_test"):
                            from ai_service import PROVIDERS
                            pid = data.get("_provider", "deepseek")
                            provider = PROVIDERS.get(pid, PROVIDERS["deepseek"])
                            api_key = data.get("_key", "")
                            model = data.get("_model", "deepseek-v4-flash")
                            if not api_key:
                                result = {"reply": "请填写 API Key"}
                            else:
                                try:
                                    # 构建请求直接测试
                                    import requests
                                    url = None
                                    if pid == "custom":
                                        base_url = data.get("_url", "")
                                        if not base_url:
                                            result = {"reply": "请配置自定义API地址"}
                                            url = None
                                        else:
                                            url = base_url.rstrip("/") + "/chat/completions"
                                    else:
                                        url = provider["base_url"].rstrip("/") + "/chat/completions"
                                    if url:
                                        payload = {"model": model, "messages": [{"role":"user","content":"回复OK"}], "max_tokens": 10, "temperature": 0}
                                        r = requests.post(url, json=payload, headers={"Authorization":"Bearer "+api_key}, timeout=10)
                                        if r.status_code == 200:
                                            data_resp = r.json()
                                            content = data_resp.get("choices",[{}])[0].get("message",{}).get("content","")
                                            if content:
                                                result = {"reply": "✅ 连通性测试通过（回复："+content[:40]+"）"}
                                            else:
                                                result = {"reply": "✅ 连通性测试通过"}
                                        elif r.status_code == 401:
                                            result = {"reply": "❌ API Key 无效"}
                                        elif r.status_code == 402:
                                            result = {"reply": "❌ 账户余额不足"}
                                        else:
                                            try:
                                                err = r.json().get("error",{}).get("message","")
                                            except:
                                                err = ""
                                            result = {"reply": "❌ 请求失败("+str(r.status_code)+")："+err[:60]}
                                except Exception as e:
                                    result = {"reply": "❌ 连接失败："+str(e)[:60]}
                        else:
                            try:
                                from ai_service import ai_svc
                                from ai_knowledge import search_knowledge
                                prompt = data.get("prompt","")
                                history = data.get("history", [])
                                # 语义搜索相关知识
                                relevant = search_knowledge(prompt, top_k=3)
                                knowledge_text = ""
                                if relevant:
                                    knowledge_text = "\n\n相关系统API参考：\n" + "\n".join(["### " + r["title"] + "\n" + r["content"] for r in relevant])
                                
                                system_prompt = "你是租房管理系统助手，名叫'租房小管家'。请根据系统数据回答用户问题。回答简洁实用，支持 Markdown 格式。"
                                if knowledge_text:
                                    system_prompt += knowledge_text
                                
                                # 构建多轮对话消息
                                messages = [{"role": "system", "content": system_prompt}]
                                for h in history:
                                    role = h.get("role", "user")
                                    if role == "assistant": role = "assistant"
                                    else: role = "user"
                                    messages.append({"role": role, "content": h.get("content","")})
                                messages.append({"role": "user", "content": prompt})
                                
                                # 用 call_with_tools 处理
                                resp = ai_svc.call_with_tools(messages, max_tokens=1024)
                                result = {"reply": resp.get("content","")}
                            except Exception as e:
                                result = {"reply": "AI 服务调用失败："+str(e)}
                    elif action=="save_chat":
                        from local_db import save_chat, update_chat
                        conv_id = data.get("id", 0)
                        title = data.get("title", "")
                        messages = data.get("messages", [])
                        if conv_id > 0:
                            update_chat(conv_id, title, messages)
                            result = {"id": conv_id}
                        else:
                            result = {"id": save_chat(title, messages)}
                    elif action=="list_chats":
                        from local_db import load_chats
                        result = load_chats()
                    elif action=="delete_chat":
                        from local_db import delete_chat
                        delete_chat(data.get("id", 0))
                        result = {"success": True}
                    elif action=="init_knowledge":
                        from ai_knowledge import init_knowledge_base
                        init_knowledge_base()
                        result = {"success": True}
                elif table=="_ocr":
                    if action=="read":
                        image = data.get("image","")
                        meter_type = data.get("meter_type", "电表")
                        from ai_service import ai_svc
                        num, err = ai_svc.read_meter_image(image, meter_type)
                        if num is not None:
                            result = {"numbers": [num], "source": "ai"}
                        else:
                            result = {"numbers": [], "source": "ai", "error": err or "AI识别失败"}
                if result is None: result = {"error":"unknown table or action"}
                return self._send_json(result)

        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e)}, 500)
def run():
    init_db()
    HTTPServer(("0.0.0.0", PORT), APIHandler).serve_forever()

if __name__ == "__main__":
    run()
