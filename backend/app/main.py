from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import bot, health, logs, markets, orders, pnl, redeem, strategy, ws
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.dashboard_broadcaster import dashboard_broadcaster
from app.services.dashboard_event_bus import subscribe_dashboard_events


configure_logging()

settings = get_settings()
app = FastAPI(title="Polymarket BTC Up/Down Bot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(bot.router, prefix="/api", tags=["bot"])
app.include_router(markets.router, prefix="/api", tags=["markets"])
app.include_router(strategy.router, prefix="/api", tags=["strategy"])
app.include_router(orders.router, prefix="/api", tags=["orders"])
app.include_router(pnl.router, prefix="/api", tags=["pnl"])
app.include_router(redeem.router, prefix="/api", tags=["redeem"])
app.include_router(logs.router, prefix="/api", tags=["logs"])
app.include_router(ws.router, tags=["websocket"])


@app.on_event("startup")
async def start_dashboard_event_subscriber() -> None:
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
