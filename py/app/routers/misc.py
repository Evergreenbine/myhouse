from datetime import date
import random

from fastapi import APIRouter, Query

import local_db as db

router = APIRouter()


@router.get("/api/chat/list")
def chat_list():
    return db.load_chats()


@router.get("/api/quote")
def quote():
    quotes = [
        "今天也是元气满满的一天！",
        "喝口水休息一下吧~",
        "慢慢来，事情会一件件理顺。",
    ]
    return {"quote": random.choice(quotes)}


@router.get("/api/weather")
def weather():
    return {"weather": "晴 28°C"}


@router.get("/api/ot-reason")
def ot_reason(ds: str | None = Query(default=None, alias="date")):
    ds = ds or date.today().isoformat()
    return {"reason": "", "date": ds}


@router.get("/api/ot-reasons-bulk")
def ot_reasons_bulk():
    return {}
