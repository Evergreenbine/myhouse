# -*- coding: utf-8 -*-
"""趣味功能模块：摸鱼语录、工作成就、心情日历"""
import random
import json
import os
from datetime import date, timedelta
from typing import Dict, List, Optional
from user_auth import load_user_config, save_user_config

QUOTES = [
    "上班不摸鱼，思想有问题 🐟",
    "只要我够努力，老板就能过上他想要的生活 💪",
    "今天的事今天做完，明天的事后天再说 🦥",
    "打工人的自我修养：吃饭要积极，下班要准时 ⏰",
    "摸鱼一时爽，一直摸鱼一直爽 🐠",
    "代码和人有一个能跑就行 🏃",
    "BUG 是程序的灵魂，摸鱼是打工的灵魂 👻",
    "我不是在摸鱼，我是在思考人生 🤔",
    "工位坐得好，工资少不了 💰",
    "上午摸摸鱼，下午打打卡，一天又过去了 ⛅",
    "周五下午的键盘声最动听 🎵",
    "先摸为敬，后摸不亏 🍺",
    "只要心态好，公司也是巴厘岛 🏖",
    "每天起床第一句：今天能不能请假 😴",
    "代码写得好不如摸鱼摸得巧 🎣",
    "老板：最近效率很高啊  我：因为我在摸鱼 😎",
    "没有摸鱼的打工是不完整的 🧩",
    "同事以为我在思考架构，其实我在想午饭吃啥 🍜",
    "加班到深夜，不如摸鱼到天明 🌙",
    "工资是老板发的，时间是自己的，摸鱼是对自己的负责 ⌛",
]

ACHIEVEMENTS = {
    "first_7days": {"name": "连续打卡7天", "icon": "🔥", "desc": "连续打卡7天不间断", "condition": lambda d: d.get("streak", 0) >= 7},
    "overtime_20h": {"name": "加班狂人", "icon": "💼", "desc": "本月累计加班超20小时", "condition": lambda d: d.get("total_ot", 0) >= 20},
    "water_8cups": {"name": "水桶认证", "icon": "💧", "desc": "连续3天喝完8杯水", "condition": lambda d: d.get("water_streak", 0) >= 3},
    "eye_rest_15m": {"name": "护眼达人", "icon": "👁", "desc": "今日护眼休息超15分钟", "condition": lambda d: d.get("eye_minutes", 0) >= 15},
    "todo_10": {"name": "效率之星", "icon": "✅", "desc": "累计完成10个待办", "condition": lambda d: d.get("todo_done", 0) >= 10},
    "punch_perfect": {"name": "全勤模范", "icon": "🏆", "desc": "本月0漏打卡", "condition": lambda d: d.get("missed", 0) == 0 and d.get("total_days", 0) >= 20},
    "friday_joy": {"name": "周五快乐", "icon": "🎉", "desc": "每到周五自动获得", "condition": lambda d: d.get("is_friday", False)},
    "overtime_40h": {"name": "肝帝认证", "icon": "💀", "desc": "本月累计加班超40小时", "condition": lambda d: d.get("total_ot", 0) >= 40},
}

MOODS = ["😊", "😫", "😤", "🤬", "😎", "🥱", "🤩", "😭", "🥳", "😐", "🤯", "❤"]

def get_random_quote() -> str:
    return random.choice(QUOTES)

def check_achievements(stats: dict, unlocked: set) -> List[dict]:
    """检查并返回新解锁的成就"""
    new_achievements = []
    for key, ach in ACHIEVEMENTS.items():
        if key not in unlocked and ach["condition"](stats):
            new_achievements.append({"key": key, "name": ach["name"], "icon": ach["icon"], "desc": ach["desc"]})
    return new_achievements

def load_mood_data() -> Dict[str, str]:
    """加载心情数据"""
    path = os.path.join(os.path.dirname(__file__), "moods.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_mood_data(data: Dict[str, str]):
    path = os.path.join(os.path.dirname(__file__), "moods.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def set_mood(ds: str, mood: str):
    data = load_mood_data()
    data[ds] = mood
    save_mood_data(data)

def get_mood(ds: str) -> Optional[str]:
    return load_mood_data().get(ds)

def load_achievements() -> set:
    """加载已解锁成就"""
    path = os.path.join(os.path.dirname(__file__), "achievements.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            pass
    return set()

def unlock_achievement(key: str):
    unlocked = load_achievements()
    unlocked.add(key)
    path = os.path.join(os.path.dirname(__file__), "achievements.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(unlocked), f, ensure_ascii=False, indent=2)
