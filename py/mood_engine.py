# -*- coding: utf-8 -*-
"""心情引擎 — 多选心情 + 压力指数 + 智能建议"""
from datetime import date, timedelta

MOOD_BASE_SCORES = {
    "😊": 2, "🥳": 0, "🤩": 1,
    "😰": 4, "😴": 5, "😤": 6, "😭": 8, "😡": 9
}

def _parse_mood(raw):
    """解析多选心情: '😊:3 😤:6' 或 '😊'"""
    if not raw: return 0
    if ':' not in raw:
        return MOOD_BASE_SCORES.get(raw.strip(), 0) / 10.0 * 10
    scores = []
    for p in raw.split():
        if ':' in p:
            e, v = p.split(':', 1)
            bs = MOOD_BASE_SCORES.get(e.strip(), 0)
            try: iv = min(int(v), 10)
            except: iv = 1
            scores.append(bs * iv / 10.0)
    return round(sum(scores) / len(scores), 1) if scores else 0

def calc_pressure(moods):
    if not moods:
        return {"pressure": 0, "trend": "stable", "suggestion": "暂无心情数据，今天也要开心哦~", "details": []}
    recent, today_ = [], date.today()
    for i in range(7):
        d = (today_ - timedelta(days=i)).isoformat()
        if d in moods:
            recent.append((d, moods[d], _parse_mood(moods[d])))
    recent.sort()
    if not recent:
        return {"pressure": 0, "trend": "stable", "suggestion": "最近没记录心情，点日历格子记录吧~", "details": []}
    avg = round(sum(r[2] for r in recent) / len(recent), 1)
    half = len(recent)//2 or 1
    a1 = sum(r[2] for r in recent[:half])/len(recent[:half])
    a2 = sum(r[2] for r in recent[half:])/len(recent[half:])
    trend = "up" if a2>a1+0.5 else ("down" if a2<a1-0.5 else "stable")
    s = ""
    if avg>=7: s="压力爆表！强烈建议去打球/健身释放，今天就别加班了 🏸"
    elif avg>=5: s="最近压力偏高，建议今天运动一下，少加一会班 💪"
    elif avg>=3: s="状态还行，保持节奏，可以适当加班但别太晚 😊"
    elif avg>=1: s="心情不错！今天效率应该很高，加个小班也不怕 🎉"
    else: s="最近超开心！继续保持，今天想干嘛就干嘛 🥳"
    return {"pressure":avg,"trend":trend,"suggestion":s,"details":[{"date":r[0],"mood":r[1],"score":r[2]} for r in recent]}

def get_smart_advice(pressure, ot_days):
    if pressure>=7 and ot_days>=3: return "⚠ 压力很大且连续加班，强烈建议今天休息或运动！"
    if pressure>=5 and ot_days>=2: return "压力偏高，今天最好去打打球放松一下 🏸"
    if pressure<=2 and ot_days>=5: return "虽然加班很多但你心态超好！今天继续加油 💪"
    if pressure<=2: return "状态极佳！今天可以高效工作，早点下班享受生活 ✨"
    if ot_days>=4: return "最近加班太多了，建议今天去打羽毛球调节一下 🏸"
    return "按自己的节奏来就好，记得劳逸结合哦~ 🐱"
