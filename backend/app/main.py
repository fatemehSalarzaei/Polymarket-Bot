from __future__ import annotations

import asyncio
import contextlib
import logging
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.admin_panel.routes import router as admin_panel_router
from app.api.routes import admin, auth, bot, health, logs, markets, orders, pnl, redeem, strategy, trading, wallet, ws
from app.core.config import get_settings
from app.core.errors import AppError, build_error_response, code_from_detail
from app.core.logging import configure_logging
from app.services.dashboard_broadcaster import dashboard_broadcaster
from app.services.dashboard_event_bus import subscribe_dashboard_events
from app.services.polymarket_errors import PolymarketHttpError
from app.services.secret_crypto import validate_encryption_key_for_startup


configure_logging()

settings = get_settings()
app = FastAPI(title="Polymarket BTC Up/Down Bot", version="0.1.0")
logger = logging.getLogger(__name__)


def _cors_allowed_origins() -> list[str]:
    origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",")]
    return [origin for origin in origins if origin]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(bot.router, prefix="/api", tags=["bot"])
app.include_router(markets.router, prefix="/api", tags=["markets"])
app.include_router(strategy.router, prefix="/api", tags=["strategy"])
app.include_router(trading.router, prefix="/api", tags=["trading"])
app.include_router(orders.router, prefix="/api", tags=["orders"])
app.include_router(pnl.router, prefix="/api", tags=["pnl"])
app.include_router(redeem.router, prefix="/api", tags=["redeem"])
app.include_router(logs.router, prefix="/api", tags=["logs"])
app.include_router(wallet.router, prefix="/api", tags=["wallet"])
app.include_router(ws.router, tags=["websocket"])
app.include_router(admin_panel_router)
app.mount("/admin-panel/static", StaticFiles(directory="app/admin_panel/static"), name="admin_panel_static")


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid4())


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    payload = build_error_response(
        exc.code,
        technical_detail=exc.technical_detail,
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = code_from_detail(exc.detail)
    payload = build_error_response(code, technical_detail=str(exc.detail), request_id=_request_id(request))
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    payload = build_error_response(
        "VALIDATION_ERROR",
        technical_detail=str(exc.errors()),
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))


@app.exception_handler(httpx.HTTPStatusError)
async def http_status_exception_handler(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    url = str(exc.request.url)
    code = "POLYMARKET_GAMMA_HTTP_ERROR" if "gamma" in url else "POLYMARKET_CLOB_HTTP_ERROR"
    payload = build_error_response(code, technical_detail=str(exc), request_id=_request_id(request))
    return JSONResponse(status_code=502, content=payload.model_dump(mode="json"))


@app.exception_handler(PolymarketHttpError)
async def polymarket_http_error_handler(request: Request, exc: PolymarketHttpError) -> JSONResponse:
    payload = build_error_response(
        exc.code,
        technical_detail=exc.technical_detail,
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unexpected_api_error")
    payload = build_error_response(
        "INTERNAL_SERVER_ERROR",
        technical_detail=str(exc),
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))


@app.on_event("startup")
async def start_dashboard_event_subscriber() -> None:
    validate_encryption_key_for_startup()

    async def forward_event(event_type: str, data: object, freshness_key: str | None) -> None:
        await dashboard_broadcaster.broadcast(event_type, data, freshness_key=freshness_key)

    app.state.dashboard_event_subscriber_task = asyncio.create_task(subscribe_dashboard_events(forward_event))


@app.on_event("shutdown")
async def stop_dashboard_event_subscriber() -> None:
    task = getattr(app.state, "dashboard_event_subscriber_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Polymarket bot backend"}
