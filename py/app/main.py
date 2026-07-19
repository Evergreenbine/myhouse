from contextlib import asynccontextmanager
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from local_db import init as init_db

from app.routers import health, misc, rental, user
from app.core import access_auth


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    access_auth.ensure_owner_account()
    yield


app = FastAPI(
    title="MyHouse API",
    version="0.2.0",
    default_response_class=Utf8JSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


PUBLIC_API_PATHS = {
    "/api/status",
    "/api/user/status",
    "/api/user/login",
    "/api/rental",
    "/api/ai/chat/stream",
}


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path in PUBLIC_API_PATHS:
        return await call_next(request)
    account = access_auth.decode_token(access_auth.token_from_headers(request.headers))
    if not account:
        return Utf8JSONResponse({"error": "登录已失效，请重新登录"}, status_code=401)
    request.state.auth_user = account
    return await call_next(request)


app.include_router(health.router)
app.include_router(user.router)
app.include_router(misc.router)
app.include_router(rental.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return Utf8JSONResponse({"error": str(exc)}, status_code=500)
