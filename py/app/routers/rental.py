import json
import queue
import threading
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.rental import RentalRequest
from app.services.rental_dispatcher import dispatch

router = APIRouter()


@router.post("/api/rental")
def rental(req: RentalRequest):
    return dispatch(req.table, req.action, req.data)


def _chat_thread_id(data: dict) -> str:
    context = data.get("session_context") if isinstance(data.get("session_context"), dict) else {}
    thread_id = str(data.get("chat_thread_id") or context.get("thread_id") or "").strip()
    if thread_id:
        return thread_id
    thread_id = "client:stream:" + uuid.uuid4().hex
    data["chat_thread_id"] = thread_id
    data["session_context"] = {**context, "thread_id": thread_id}
    return thread_id


def _sse(event: str, data: dict) -> str:
    return "event: " + event + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@router.post("/api/ai/chat/stream")
def ai_chat_stream(req: RentalRequest):
    data = dict(req.data or {})
    thread_id = _chat_thread_id(data)
    events: queue.Queue = queue.Queue()

    try:
        from app.services.ai_orchestrator import add_status_listener, remove_status_listener
    except Exception:
        add_status_listener = None
        remove_status_listener = None

    def on_status(item):
        events.put(("status", item))

    def worker():
        if add_status_listener:
            add_status_listener(thread_id, on_status)
        try:
            events.put(("status", {"event": "stream_start", "text": "正在开始处理", "payload": {}}))
            result = dispatch(req.table, req.action, data)
            events.put(("result", result or {}))
        except Exception as exc:
            events.put(("error", {"message": str(exc)}))
        finally:
            if remove_status_listener:
                remove_status_listener(thread_id, on_status)
            events.put(("done", {}))

    threading.Thread(target=worker, daemon=True).start()

    def generate():
        while True:
            event, payload = events.get()
            yield _sse(event, payload)
            if event == "done":
                break

    return StreamingResponse(generate(), media_type="text/event-stream")
