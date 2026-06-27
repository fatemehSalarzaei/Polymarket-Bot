from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import bot, health, logs, markets, orders, pnl, strategy, ws
from app.core.config import get_settings
from app.core.logging import configure_logging


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
app.include_router(logs.router, prefix="/api", tags=["logs"])
app.include_router(ws.router, tags=["websocket"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Polymarket bot backend"}
