# -*- coding: utf-8 -*-
"""时间胶囊 — 每日心情 & 笔记存储"""
from local_db import _conn

def init():
    c = _conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS time_capsule (
            date TEXT PRIMARY KEY,
            mood TEXT DEFAULT '',
            note TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
    """)
    c.commit()
    c.close()

def get_capsule(date_str):
    c = _conn()
    row = c.execute("SELECT mood, note, updated_at FROM time_capsule WHERE date=?", (date_str,)).fetchone()
    c.close()
    if row:
        return {"mood": row["mood"] or "", "note": row["note"] or "", "updated_at": row["updated_at"] or ""}
    return {"mood": "", "note": "", "updated_at": ""}

def save_capsule(date_str, mood="", note=""):
    from datetime import datetime
    c = _conn()
    c.execute("INSERT OR REPLACE INTO time_capsule (date, mood, note, updated_at) VALUES (?,?,?,?)",
              (date_str, mood.strip(), note.strip(), datetime.now().isoformat()))
    c.commit()
    c.close()

def get_month_capsules(month_prefix):
    """获取某月所有胶囊，格式 YYYY-MM"""
    c = _conn()
    rows = c.execute("SELECT date, mood FROM time_capsule WHERE date LIKE ?", (month_prefix + '%',)).fetchall()
    c.close()
    return {r["date"]: r["mood"] for r in rows}

init()
