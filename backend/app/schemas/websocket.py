from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class MarketTick(BaseModel):
    token_id: str
    event_type: str | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    spread: Decimal | None = None
    raw_payload: dict[str, Any]
    received_at: datetime


class BtcPriceTick(BaseModel):
    symbol: str = "btc/usd"
    value: Decimal
    source: str = "polymarket_rtds_chainlink"
    source_timestamp: datetime | None = None
    received_at: datetime
    raw_payload: dict[str, Any]


class BotStatus(BaseModel):
    running: bool = False
    market_ws_fresh: bool = False
    rtds_fresh: bool = False
    background_workers_required: bool = True
    message: str | None = None


class RiskStatus(BaseModel):
    trading_enabled: bool = False
    kill_switch_active: bool = False
    geoblock_blocked: bool | None = None


class DashboardError(BaseModel):
    code: str
    message: str


class DashboardWsEvent(BaseModel):
    type: Literal[
        "market_tick",
        "btc_price_tick",
        "strategy_decision",
        "order_update",
        "bot_status",
        "risk_status",
        "pnl_summary",
        "error",
    ]
    data: dict[str, Any] = Field(default_factory=dict)
