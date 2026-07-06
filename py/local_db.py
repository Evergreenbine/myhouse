# -*- coding: utf-8 -*-
"""本地 SQLite 数据库 — 存储应用配置、加班理由等"""
import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "local.db")

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    c = _conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS ot_reasons (
            date TEXT PRIMARY KEY,
            reason TEXT DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_config (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_user (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            messages TEXT DEFAULT '[]',
            created_at TEXT DEFAULT ''
        )
    """)
    # migrate: add archived column if not exists
    try:
        c.execute('ALTER TABLE chat_history ADD COLUMN archived INTEGER DEFAULT 0')
    except:
        pass
    c.commit()
    c.close()

# === 加班理由 ===
def get_reason(date_str):
    c = _conn()
    row = c.execute("SELECT reason FROM ot_reasons WHERE date=?", (date_str,)).fetchone()
    c.close()
    return row["reason"] if row else ""

def save_reason(date_str, reason):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO ot_reasons (date, reason) VALUES (?,?)", (date_str, reason.strip()))
    c.commit()
    c.close()

def get_all_reasons():
    c = _conn()
    rows = c.execute("SELECT date, reason FROM ot_reasons").fetchall()
    c.close()
    return {r["date"]: r["reason"] for r in rows}

# === 用户配置 ===
def get_config(key, default=""):
    c = _conn()
    row = c.execute("SELECT value FROM user_config WHERE key=?", (key,)).fetchone()
    c.close()
    return row["value"] if row else default

def set_config(key, value):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO user_config (key, value) VALUES (?,?)", (key, str(value)))
    c.commit()
    c.close()

def get_all_config():
    c = _conn()
    rows = c.execute("SELECT key, value FROM user_config").fetchall()
    c.close()
    return {r["key"]: r["value"] for r in rows}

# === app_user 表（基本信息 / 用户设置，key-value 存储） ===
def save_app_user(data: dict):
    """将 dict 逐字段写入 app_user 表"""
    c = _conn()
    for k, v in data.items():
        val = str(v) if not isinstance(v, str) else v
        c.execute("INSERT OR REPLACE INTO app_user (key, value) VALUES (?,?)", (k, val))
    c.commit()
    c.close()

def load_app_user() -> dict:
    """从 app_user 表读取全部字段，返回 dict"""
    c = _conn()
    rows = c.execute("SELECT key, value FROM app_user").fetchall()
    c.close()
    return {r["key"]: r["value"] for r in rows}


def get_all_reasons_for_month(month):
    """获取指定月份(YYYY-MM)的所有加班理由"""
    c = _conn()
    try:
        rows = c.execute("SELECT date, reason FROM ot_reasons WHERE date LIKE ?", (month + '%',)).fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        c.close()
def migrate_json_to_sqlite():
    """将 user_config.json 中的基本配置迁移到 app_user 表（仅首次）"""
    existing = load_app_user()
    if existing:
        return
    _JSON_PATH = os.path.join(os.path.dirname(__file__), "user_config.json")
    if not os.path.exists(_JSON_PATH):
        return
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
        keys = ["empno","empname","car_plate","base_salary","lunch_start","lunch_end",
                "dinner_start","dinner_end","api_key","ai_model","ai_persona",
                "water_enabled","eye_enabled","water_ml","avatar_path"]
        data = {k: old[k] for k in keys if k in old}
        if data:
            save_app_user(data)
            print("Migration: copied user_config.json to app_user table")
    except Exception as e:
        print(f"Migration skipped: {e}")

# === 聊天历史 ===
def save_chat(conv_id, title, messages, archived=0):
    c = _conn()
    c.execute("INSERT OR REPLACE INTO chat_history (id, title, messages, created_at, archived) VALUES (?,?,?,?,?)",
              (conv_id, title, json.dumps(messages, ensure_ascii=False), datetime.now().isoformat(), 1 if archived else 0))
    c.commit()
    c.close()

def load_chats():
    c = _conn()
    rows = c.execute("SELECT id, title, messages, created_at, archived FROM chat_history ORDER BY created_at DESC LIMIT 50").fetchall()
    c.close()
    return [{"id": r["id"], "title": r["title"], "messages": json.loads(r["messages"]), "time": r["created_at"], "archived": bool(r["archived"])} for r in rows]

def delete_chat(conv_id):
    c = _conn()
    c.execute("DELETE FROM chat_history WHERE id=?", (conv_id,))
    c.commit()
    c.close()

# 启动时初始化 + 迁移旧数据
init()
migrate_json_to_sqlite()
_JSON_FILE = os.path.join(os.path.dirname(__file__), "data", "ot_reasons.json")
if os.path.exists(_JSON_FILE):
    try:
        with open(_JSON_FILE, 'r', encoding='utf-8') as f:
            old = json.load(f)
        for dt, reason in old.items():
            save_reason(dt, reason)
        os.rename(_JSON_FILE, _JSON_FILE + ".bak")
        print("Migration: moved ot_reasons.json to SQLite")
    except:
        pass
