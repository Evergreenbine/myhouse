# -*- coding: utf-8 -*-
"""AI 后台关怀系统 — 默默记录专注时长，定时分析提醒"""
import json
import os
import urllib.request
import threading
import time as _time
from datetime import datetime, date, timedelta
from user_auth import load_user_config, save_user_config

CONFIG_DIR = os.path.dirname(__file__)
AI_CFG_PATH = os.path.join(CONFIG_DIR, "ai_config.json")
FOCUS_LOG_PATH = os.path.join(CONFIG_DIR, "focus_log.json")


def _get_ai_config():
    if os.path.exists(AI_CFG_PATH):
        try:
            with open(AI_CFG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def _call_ai(prompt, max_tokens=512):
    """调用 DeepSeek"""
    cfg = _get_ai_config()
    api_key = cfg.get("api_key", "")
    model = cfg.get("model", "deepseek-chat")
    if not api_key:
        return None

    try:
        data = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是哈基米曼波，一只温暖贴心的猫咪AI助手。回答简洁温馨，像朋友一样关心主人。用数据说话。"},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": 0.8,
        }).encode()

        req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        return result["choices"][0]["message"]["content"]
    except:
        return None


def _load_focus_log():
    if os.path.exists(FOCUS_LOG_PATH):
        try:
            with open(FOCUS_LOG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def _save_focus_log(log):
    with open(FOCUS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def start_focus():
    """开始专注"""
    cfg = load_user_config()
    if not cfg:
        return
    now = datetime.now()
    cfg.focus_start = now.isoformat()
    cfg.focus_date = date.today().isoformat()
    save_user_config(cfg)


def stop_focus():
    """停止专注，累计时长"""
    cfg = load_user_config()
    if not cfg or not cfg.focus_start:
        return 0
    try:
        start = datetime.fromisoformat(cfg.focus_start)
        minutes = int((datetime.now() - start).total_seconds() / 60)
    except:
        minutes = 0
    if minutes <= 0:
        cfg.focus_start = ""
        save_user_config(cfg)
        return 0

    today = date.today().isoformat()
    if cfg.focus_date != today:
        cfg.focus_minutes_today = 0
        cfg.focus_date = today
    cfg.focus_minutes_today += minutes
    cfg.focus_start = ""

    # 记录到日志
    log = _load_focus_log()
    if today not in log:
        log[today] = []
    log[today].append({
        "start": start.strftime("%H:%M"),
        "end": datetime.now().strftime("%H:%M"),
        "minutes": minutes,
    })
    _save_focus_log(log)

    save_user_config(cfg)
    return minutes


def get_today_focus():
    """获取今日专注"""
    cfg = load_user_config()
    if not cfg:
        return 0
    today = date.today().isoformat()
    if cfg.focus_date != today:
        return 0
    current = 0
    if cfg.focus_start:
        try:
            start = datetime.fromisoformat(cfg.focus_start)
            current = int((datetime.now() - start).total_seconds() / 60)
        except:
            pass
    return cfg.focus_minutes_today + current


def get_week_focus():
    """获取本周专注数据"""
    log = _load_focus_log()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    total = 0
    daily = {}
    for i in range(7):
        d = week_start + timedelta(days=i)
        ds = d.isoformat()
        day_min = sum(s.get("minutes", 0) for s in log.get(ds, []))
        if ds == today.isoformat():
            day_min = get_today_focus()
        daily[ds] = day_min
        total += day_min
    return {"total": total, "daily": daily}


def start_ai_care(app_ref):
    """启动 AI 后台关怀线程"""
    def _run():
        last_check_hour = -1
        last_summary_date = ""
        last_water_check = -1
        while True:
            try:
                now = datetime.now()
                cur_date = date.today().isoformat()
                h, m = now.hour, now.minute

                # 专注超2小时提醒
                if h != last_check_hour and 9 <= h <= 20:
                    last_check_hour = h
                    cfg = load_user_config()
                    if cfg and cfg.focus_start:
                        minutes = get_today_focus()
                        if minutes >= 120:
                            tip = _call_ai(f"主人专注{minutes}分钟了，用一句话催他休息。")
                            if tip and hasattr(app_ref, 'page'):
                                app_ref._toast("哈基米 关怀", tip)

                # 喝水监督（15:00检查）
                if h == 15 and m == 0 and h != last_water_check:
                    last_water_check = h
                    cfg = load_user_config()
                    if cfg and cfg.water_date == cur_date:
                        cups = cfg.water_count
                        if cups < 4:
                            tip = _call_ai(f"主人今天才喝{cups}杯水，用毒舌+关心的语气催他喝水。")
                            if tip and hasattr(app_ref, 'page'):
                                app_ref._toast("哈基米 喝水监督", tip)

                # 17:00 下班心情
                if h == 17 and m == 0 and cur_date != last_summary_date:
                    last_summary_date = cur_date
                    focus = get_today_focus()
                    ot_hours = 0.0
                    if hasattr(app_ref, 'analysis_map') and cur_date in app_ref.analysis_map:
                        ot_hours = app_ref.analysis_map[cur_date].overtime_hours
                    week_ot = 0.0
                    if hasattr(app_ref, 'analysis_map'):
                        week_start = date.today() - timedelta(days=date.today().weekday())
                        for i in range(5):
                            ds = (week_start + timedelta(days=i)).isoformat()
                            if ds in app_ref.analysis_map:
                                week_ot += app_ref.analysis_map[ds].overtime_hours
                    prompt = f"下午5点下班时间！今日专注{int(focus)}分钟，加班{ot_hours:.1f}h，本周累计加班{week_ot:.1f}h。请用一句话暖心总结+鼓励+提醒带伞/穿衣（如果天气不好）。"
                    summary = _call_ai(prompt)
                    if summary and hasattr(app_ref, 'page'):
                        app_ref._toast("哈基米 下班关怀", summary)

                _time.sleep(50)
            except:
                _time.sleep(50)

    threading.Thread(target=_run, daemon=True).start()
