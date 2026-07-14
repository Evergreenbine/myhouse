# -*- coding: utf-8 -*-
"""Compatibility launcher for the FastAPI backend.

Existing scripts can still run:

    python D:/code/myhouse/py/api_server.py

The real application now lives in app/main.py.
"""

from app.core.config import DEFAULT_HOST, DEFAULT_PORT
from app.main import app
from app.services.ai_context import build_rental_ai_context as _build_rental_ai_context

PORT = DEFAULT_PORT


def run(host=DEFAULT_HOST, port=DEFAULT_PORT):
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
