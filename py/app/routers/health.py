from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/status")
def status():
    return {"status": "ok", "time": datetime.now().isoformat()}

