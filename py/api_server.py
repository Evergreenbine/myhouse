# -*- coding: utf-8 -*-
import json, os, sys, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import date, datetime, timedelta
from config import DB_CONFIG
from database import get_connection, query_work_records_range
from punch_card import generate_sql
from attendance import DayAnalysis, get_company_month_range, get_company_month_label
from user_auth import load_user_config, save_user_config
from local_db import load_app_user, save_app_user, get_reason, save_reason
from calendar_2026 import get_holiday_name
from car_db import query_car_records, update_car_record
from tools import TOOLS, tool_executor
from ai_service import ai_svc
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

    

    

    def _handle_ot_reasons_bulk(self, qs):
        month = qs.get("month", [date.today().strftime("%Y-%m")])[0]
        reasons = {}
        try:
            from local_db import get_all_reasons_for_month
            reasons = get_all_reasons_for_month(month)
        except:
            pass
        return self._send_json(reasons)


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
                        "ai_nickname": _get("ai_nickname","哈基米"),
                        "user_nickname": _get("user_nickname","主人"),
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

            elif path == "/api/attendance/month":
                ref_date = date.today()
                m_str = qs.get("date", [None])[0]
                if m_str:
                    ref_date = date.fromisoformat(m_str)
                cfg = load_user_config()
                if not cfg:
                    return self._send_json({"error":"未登录"}, 401)
                empno = self._get_empno()
                s, e = get_company_month_range(ref_date)
                recs = query_work_records_range(empno, s.isoformat(), e.isoformat())
                result = {"month_label": get_company_month_label(ref_date), "days": {}}
                d = s
                while d <= e:
                    ds = d.isoformat()
                    a = DayAnalysis(d, recs.get(ds, []), cfg)
                    result["days"][ds] = {
                        "type": a.day_type_label, "is_rest": a.is_rest,
                        "is_makeup": a.is_makeup,
                        "overtime_hours": a.overtime_hours, "overtime_pay": a.overtime_pay,
                        "card_count": a.card_count, "required_cards": a.required_cards,
                        "missed": a.missed and d < date.today(),
                        "holiday_name": get_holiday_name(d),
                    }
                    d += timedelta(days=1)
                return self._send_json(result)

            elif path == "/api/attendance/records":
                ds = qs.get("date", [date.today().isoformat()])[0]
                cfg = load_user_config()
                if not cfg:
                    return self._send_json([], 401)
                empno = self._get_empno()
                recs = query_work_records_range(empno, ds, ds)
                items = []
                for r in recs.get(ds, []):
                    wt = r.get("worktime")
                    time_str = ""
                    if wt:
                        if hasattr(wt, "strftime"):
                            time_str = wt.strftime("%H:%M:%S")
                        else:
                            time_str = str(wt)[-8:]
                    items.append({"id": r.get("id",""), "time": time_str,
                        "remark": r.get("remark", r.get("backup1",""))})
                return self._send_json(items)

            elif path.startswith('/api/car/records'):
                pq = urlparse(self.path).query
                pqs = parse_qs(pq)
                df = pqs.get('from', [date.today().replace(day=1).isoformat()])[0]
                dt = pqs.get('to', [date.today().isoformat()])[0]
                cfg = load_user_config()
                plate = cfg.car_plate if cfg else '?S0Q780'
                try:
                    from calendar import monthrange
                    all_rows = []
                    ds = date.fromisoformat(df)
                    de = date.fromisoformat(dt)
                    ym = ds.year * 100 + ds.month
                    yme = de.year * 100 + de.month
                    while ym <= yme:
                        y = ym // 100
                        m = ym % 100
                        yrm = f'{y:04d}{m:02d}'
                        try:
                            rows = query_car_records(plate, yrm)
                            all_rows.extend(rows)
                        except:
                            pass
                        if m == 12:
                            ym = (y + 1) * 100 + 1
                        else:
                            ym += 1
                    filtered = [r for r in all_rows if df <= str(r.get('ch_crosstime',''))[:10] <= dt]
                    mapped = []
                    for r in filtered:
                        ct = r.get('ch_crosstime')
                        if hasattr(ct, 'isoformat'):
                            ct_str = ct.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            ct_str = str(ct)
                        date_part = ct_str[:10]
                        direction = '进' if r.get('ch_out') == 0 else '出'
                        mapped.append({
                            'ch_id': r.get('ch_id', ''),
                            'date': date_part,
                            'time': ct_str,
                            'direction': direction,
                        })
                    return self._send_json(mapped)
                except Exception as e:
                    traceback.print_exc()
                    return self._send_json([])

            elif path.startswith('/api/car/abnormal'):
                pq = urlparse(self.path).query
                pqs = parse_qs(pq)
                df = pqs.get('from', [date.today().replace(day=1).isoformat()])[0]
                dt = pqs.get('to', [date.today().isoformat()])[0]
                try:
                    empno = self._get_empno()
                    punch_recs = query_work_records_range(empno, df, dt)
                    car_data = []
                    # 直接调用内部逻辑获取车辆记录（避免单线程HTTP自调用死锁）
                    from calendar import monthrange
                    cfg_l = load_user_config()
                    plate_l = cfg_l.car_plate if cfg_l else '粤S0Q780'
                    all_rows_l = []
                    ds_l = date.fromisoformat(df)
                    de_l = date.fromisoformat(dt)
                    ym_l = ds_l.year * 100 + ds_l.month
                    yme_l = de_l.year * 100 + de_l.month
                    while ym_l <= yme_l:
                        y = ym_l // 100
                        m = ym_l % 100
                        yrm = f'{y:04d}{m:02d}'
                        try:
                            rows_l = query_car_records(plate_l, yrm)
                            all_rows_l.extend(rows_l)
                        except:
                            pass
                        if m == 12:
                            ym_l = (y + 1) * 100 + 1
                        else:
                            ym_l += 1
                    filtered_l = [r for r in all_rows_l if df <= str(r.get('ch_crosstime',''))[:10] <= dt]
                    for r in filtered_l:
                        ct_l = r.get('ch_crosstime')
                        if hasattr(ct_l, 'isoformat'):
                            ct_str_l = ct_l.strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            ct_str_l = str(ct_l)
                        date_part_l = ct_str_l[:10]
                        direction_l = '进' if r.get('ch_out') == 0 else '出'
                        car_data.append({
                            'ch_id': r.get('ch_id', ''),
                            'date': date_part_l,
                            'time': ct_str_l,
                            'direction': direction_l,
                        })
                    abnormal = []
                    # 从基本信息读取班次时间
                    lunch_start = '12:05'
                    lunch_end = '13:05'
                    dinner_start = '17:30'
                    dinner_end = '18:00'
                    try:
                        ul = load_app_user()
                        if ul:
                            if ul.get('lunch_start'): lunch_start = ul['lunch_start']
                            if ul.get('lunch_end'): lunch_end = ul['lunch_end']
                            if ul.get('dinner_start'): dinner_start = ul['dinner_start']
                            if ul.get('dinner_end'): dinner_end = ul['dinner_end']
                    except:
                        pass
                    for cr in car_data:
                        ct = cr.get('time', '')
                        cd = cr.get('date', '')
                        punch_times = []
                        if cd in punch_recs:
                            for pr in punch_recs[cd]:
                                wt = pr.get('worktime')
                                if wt:
                                    if hasattr(wt, 'strftime'):
                                        punch_times.append(wt.strftime('%H:%M'))
                                    else:
                                        punch_times.append(str(wt)[-5:])
                        time_part = ct[11:16] if len(ct) > 16 else ct
                        is_abnormal = True
                        if punch_times:
                            day_type_label = ''
                            try:
                                cfg_l2 = load_user_config()
                                a = DayAnalysis(date.fromisoformat(cd), punch_recs.get(cd, []), cfg_l2)
                                day_type_label = a.day_type_label
                            except:
                                pass
                            if '休息日' in day_type_label or '节假日' in day_type_label:
                                is_abnormal = False
                            else:
                                if lunch_start <= time_part <= lunch_end:
                                    is_abnormal = False
                                else:
                                    has_overtime = any(t >= dinner_end for t in punch_times)
                                    if has_overtime:
                                        if dinner_start <= time_part <= dinner_end:
                                            is_abnormal = False
                                        elif punch_times and time_part > max(punch_times):
                                            is_abnormal = False
                        if is_abnormal:
                            abnormal.append(cr)
                    return self._send_json(abnormal)
                except:
                    return self._send_json([])
            elif path.startswith('/api/punch/times-range'):
                pq = urlparse(self.path).query
                pqs = parse_qs(pq)
                df = pqs.get('from', [date.today().replace(day=1).isoformat()])[0]
                dt = pqs.get('to', [date.today().isoformat()])[0]
                empno = self._get_empno()
                try:
                    recs = query_work_records_range(empno, df, dt)
                    result = {}
                    for ds, records in recs.items():
                        times = []
                        for r in records:
                            wt = r.get('worktime')
                            if wt:
                                if hasattr(wt, 'strftime'):
                                    times.append(wt.strftime('%H:%M:%S'))
                                else:
                                    times.append(str(wt)[-8:])
                        if times:
                            cfg = load_user_config()
                            a = DayAnalysis(date.fromisoformat(ds), records, cfg)
                            result[ds] = {
                                'times': times,
                                'day_type': a.day_type_label,
                                'earliest': times[0] if times else '',
                                'latest': times[-1] if times else '',
                            }
                    return self._send_json(result)
                except Exception as e:
                    return self._send_json({})
            elif path == "/api/chat/list":
                from local_db import load_chats
                return self._send_json(load_chats())
            elif path == "/api/quote":
                import random
                qs_list = ["今天也是元气满满的一天！", "喝口水休息一下吧~", "摸鱼也是生产力！"]
                return self._send_json({"quote": random.choice(qs_list)})

            elif path == "/api/weather":
                return self._send_json({"weather": "☀️ 晴 28°C"})

            elif path == "/api/ot-reason":
                ds = qs.get("date", [date.today().isoformat()])[0]
                r = get_reason(ds)
                return self._send_json({"reason": r, "date": ds})

            elif path == "/api/ot-reasons-bulk":
                return self._handle_ot_reasons_bulk(qs)

            elif path == "/api/punch/remarks":
                empno = self._get_empno()
                remarks = []
                try:
                    conn = get_connection()
                    c = conn.cursor()
                    from dateutil.relativedelta import relativedelta
                    three_months_ago = (date.today() - relativedelta(months=3)).strftime('%Y-%m-%d')
                    c.execute("SELECT DISTINCT remark FROM kq_workrecord WHERE empno=? AND remark IS NOT NULL AND remark!='' AND workdate>=? ORDER BY remark", (str(empno), three_months_ago + ' 00:00:00'))
                    remarks = [r[0] for r in c.fetchall() if r[0]]
                    conn.close()
                except:
                    pass
                if not remarks:
                    remarks = ["公司大门打卡","办公室内打卡","手机APP打卡","宿舍打卡","食堂打卡","外出打卡"]
                return self._send_json(remarks)

            elif path == "/api/user/status":
                cfg = load_user_config()
                if cfg and cfg.is_logged_in:
                    return self._send_json({"logged_in": True, "empno": cfg.empno, "empname": cfg.empname})
                return self._send_json({"logged_in": False})

        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}

            if path == "/api/skills/reload":
                from skill_manager import skill_mgr
                skill_mgr.hot_reload()
                return self._send_json({"status": "ok", "skills": skill_mgr.list_skills()})
            if path == "/api/ai/chat":
                prompt = body.get("prompt", "")
                persona = body.get("persona", "warm")
                use_tools = body.get("use_tools", False)
                history = body.get("history", [])
                req_model = body.get("model", "")

                p_desc = "温柔暖心，喜欢鼓励用户。" if persona == "warm" else "毒舌傲娇，喜欢吐槽用户。"
                rules_content = ""
                try:
                    with open(os.path.join(os.path.dirname(__file__), 'business_rules.md'), 'r', encoding='utf-8') as rf:
                        rules_content = rf.read()
                except:
                    pass

                # 语义匹配 Skill，注入到 system prompt
                skill_context = ""
                try:
                    from skill_manager import skill_mgr
                    skill_context = skill_mgr.format_for_prompt(prompt)
                except:
                    pass

                ai_name, user_name = "哈基米", "主人"
                try:
                    from local_db import load_app_user
                    local = load_app_user()
                    if local:
                        ai_name = local.get("ai_nickname", "哈基米")
                        user_name = local.get("user_nickname", "主人")
                except:
                    pass

                sys_prompt = (
                    "你是一个名叫" + ai_name + "的猫咪AI助手，运行在一个加班考勤管理应用中。\n"
                    "称呼用户为\"" + user_name + "\"。\n"
                    "当前日期: 2026年7月4日，星期六。\n"
                    "你的性格是" + persona + "，" + p_desc + "\n\n"
                    "=== 核心规则（必须遵守）=== \n"
                    "1. 用户叫\"吴钦腾\"，工号M03141。\n"
                    "2. **休息日/节假日 不等于 不用上班**。只要当天有打卡记录，就说明用户加班了。\n"
                    "3. 查询数据必须通过工具函数，绝对不要自行编造或猜测数据。\n"
                    "4. 回答用中文，保持轻松可爱的猫咪语气，适当使用emoji。\n"
                    + skill_context + "\n"
                    "=== 业务规则 ===\n" + rules_content
                )
                if body.get("messages"):
                    messages = body["messages"]
                else:
                    messages = [{"role": "system", "content": sys_prompt}]
                    for h in history:
                        messages.append(h)
                    messages.append({"role": "user", "content": prompt})

                if use_tools:
                    thinking = []
                    for _ in range(5):
                        try:
                            resp = ai_svc.call_with_tools(messages, tools=TOOLS, timeout=60, model=req_model)
                        except Exception as e:
                            traceback.print_exc()
                            thinking.append("❌ API调用异常: " + str(e)[:100])
                            return self._send_json({"reply": "🐱 哈基米卡住了... " + str(e)[:80], "thinking": thinking})
                        content = resp.get("content", "")
                        tcalls = resp.get("tool_calls")
                        if tcalls:
                            messages.append({"role": "assistant", "content": content or "", "tool_calls": tcalls})
                            for t in tcalls:
                                fn = t["function"]["name"]
                                try:
                                    args = json.loads(t["function"]["arguments"])
                                except:
                                    args = {}
                                thinking.append("🔧 " + fn + "(" + str(args)[:60] + ")")
                                try:
                                    result = tool_executor.execute(fn, args)
                                    thinking.append("   ✅ 结果长度: " + str(len(result)))
                                except Exception as e:
                                    traceback.print_exc()
                                    result = f"工具执行出错: {str(e)[:150]}"
                                    thinking.append("   ❌ 出错: " + str(e)[:60])
                                messages.append({"role": "tool", "tool_call_id": t["id"], "content": result})
                        else:
                            return self._send_json({"reply": content, "thinking": thinking, "messages": messages})
                    return self._send_json({"reply": "操作步骤过多", "thinking": thinking, "messages": messages})
                else:
                    result = ai_svc.call(prompt, system_prompt=sys_prompt, max_tokens=512)
                    return self._send_json({"reply": result, "thinking": []})

            if path == "/api/ai/chat/stream":
                prompt = body.get("prompt", "")
                model = body.get("model", "")
                persona = body.get("personality", "warm")
                history = body.get("history", [])
                sp = "你是哈基米，一个可爱的AI助手..."
                if persona == "tsundere":
                    sp = "你是哈基米，傲娇的AI助手..."
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    for token in ai_svc.call_stream(prompt, system_prompt=sp, max_tokens=1024, temperature=0.7, timeout=60):
                        self.wfile.write(("data: " + json.dumps({"token": token}) + "\n\n").encode("utf-8"))
                        self.wfile.flush()
                except Exception as ex:
                    self.wfile.write(("data: " + json.dumps({"error": str(ex)}) + "\n\n").encode("utf-8"))
                self.wfile.write(("data: [DONE]\n\n").encode("utf-8"))
                return

            elif path == "/api/chat/save":
                from local_db import save_chat
                cid = body.get("id", 0)
                title = body.get("title", "")
                msgs = body.get("messages", [])
                archived = body.get("archived", False)
                save_chat(cid, title, msgs, archived=archived)
                return self._send_json({"success": True})
            elif path == "/api/chat/delete":
                from local_db import delete_chat
                cid = body.get("id", 0)
                delete_chat(cid)
                return self._send_json({"success": True})
            elif path == "/api/chat/archive":
                from local_db import save_chat, load_chats
                cid = body.get("id", 0)
                archived = body.get("archived", True)
                for chat in load_chats():
                    if chat["id"] == cid:
                        save_chat(cid, chat["title"], chat["messages"], archived=archived)
                        return self._send_json({"success": True})
                return self._send_json({"success": False, "error": "not found"})
            elif path == "/api/punch":
                ds = body.get("date", date.today().isoformat())
                t = body.get("time", "08:00:00")
                r = body.get("remark", "")
                try:
                    sqls = generate_sql(ds, t, r)
                    conn = get_connection()
                    c = conn.cursor()
                    for sql in sqls:
                        c.execute(sql)
                    conn.commit()
                    conn.close()
                    return self._send_json({"success": True, "msg": "补卡成功 " + t})
                except Exception as e:
                    return self._send_json({"success": False, "msg": str(e)})

            elif path == "/api/punch/update":
                rid = body.get("id")
                t = body.get("time", "")
                r = body.get("remark", "")
                try:
                    conn = get_connection()
                    c = conn.cursor()
                    nt = "1900-01-01 " + t if "1900" not in t else t
                    c.execute("UPDATE kq_workrecord SET worktime=?, remark=? WHERE id=?", (nt, r, rid))
                    conn.commit()
                    conn.close()
                    return self._send_json({"success": True})
                except Exception as e:
                    return self._send_json({"success": False, "msg": str(e)})

            elif path == "/api/ot-reason":
                ds = body.get("date", date.today().isoformat())
                reason = body.get("reason", "")
                save_reason(ds, reason)
                return self._send_json({"success": True})

            
            elif path == "/api/user/update":
                save_app_user(body)
                cfg = load_user_config()
                if not cfg:
                    return self._send_json({"success": True})
                for key in ["empname","car_plate","base_salary","water_enabled","eye_enabled",
                    "water_ml","avatar_path","api_key","openai_key","zhipu_key",
                    "custom_api_key","custom_base_url","custom_model","ai_provider",
                    "ai_model","ai_persona","lunch_start","lunch_end","dinner_start","dinner_end"]:
                    if key in body:
                        setattr(cfg, key, body[key])
                if "password" in body and body["password"]:
                    import hashlib
                    cfg.password_hash = hashlib.sha256(body["password"].encode()).hexdigest()
                save_user_config(cfg)
                return self._send_json({"success": True})

            elif path == "/api/login":
                from user_auth import login as dl
                cfg = dl(body.get("empno",""), body.get("password",""))
                if cfg:
                    return self._send_json({"success": True, "empno": cfg.empno})
                return self._send_json({"success": False, "msg": "工号或密码错误"})

            elif path == "/api/register":
                from user_auth import register as dr
                cfg = dr(body.get("empno",""), body.get("empname",""),
                    body.get("car_plate",""), float(body.get("base_salary",20.5)),
                    body.get("password",""))
                if cfg:
                    return self._send_json({"success": True, "empno": cfg.empno})
                return self._send_json({"success": False, "msg": "注册失败"})

            elif path == "/api/car/records":
                yrm = body.get("year_month", date.today().strftime("%Y%m"))
                plate = body.get("plate","")
                if not plate:
                    cfg = load_user_config()
                    plate = cfg.car_plate if cfg else "粤S0Q780"
                rows = query_car_records(plate, yrm)
                return self._send_json(rows)


            elif path == "/api/car/update":
                cid = body.get("ch_id","")
                yrm = body.get("year_month", date.today().strftime("%Y%m"))
                nt = body.get("new_time")
                no = body.get("new_out")
                return self._send_json({"success": update_car_record(cid, yrm, nt, no)})

            elif path == "/api/focus/start":
                cfg = load_user_config()
                if cfg:
                    cfg.focus_start = datetime.now().isoformat()
                    cfg.focus_date = date.today().isoformat()
                    cfg.focus_minutes_today = cfg.focus_minutes_today or 0
                    save_user_config(cfg)
                return self._send_json({"success": True})

            elif path == "/api/focus/stop":
                cfg = load_user_config()
                if cfg and cfg.focus_start:
                    start = datetime.fromisoformat(cfg.focus_start)
                    mins = int((datetime.now() - start).total_seconds() / 60)
                    if cfg.focus_date == date.today().isoformat():
                        cfg.focus_minutes_today = (cfg.focus_minutes_today or 0) + mins
                    else:
                        cfg.focus_minutes_today = mins
                        cfg.focus_date = date.today().isoformat()
                    cfg.focus_start = ""
                    save_user_config(cfg)
                    return self._send_json({"minutes": cfg.focus_minutes_today})
                return self._send_json({"minutes": 0})

        except Exception as e:
            traceback.print_exc()
            return self._send_json({"error": str(e)}, 500)

def run():
    HTTPServer(("0.0.0.0", PORT), APIHandler).serve_forever()

if __name__ == "__main__":
    run()
