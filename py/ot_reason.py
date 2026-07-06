# -*- coding: utf-8 -*-
"""加班理由存储"""
import json
import os

_FILE = os.path.join(os.path.dirname(__file__), "data", "ot_reasons.json")

def _load():
    if os.path.exists(_FILE):
        with open(_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(data):
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_reason(date_str):
    return _load().get(date_str, "")

def save_reason(date_str, reason):
    data = _load()
    data[date_str] = reason.strip()
    _save(data)
