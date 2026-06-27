from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class OrderbookLevel(BaseModel):
    price: Decimal
    size: Decimal


class OrderbookDTO(BaseModel):
    market: str | None = None
    token_id: str
    source_timestamp: datetime | None = None
    book_hash: str | None = None
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]
    min_order_size: Decimal | None = None
    tick_size: Decimal | None = None
    neg_risk: bool | None = None
    last_trade_price: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    midpoint: Decimal | None = None
    spread: Decimal | None = None
    raw_payload: dict[str, Any]


class OrderbookSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    token_id: str
    outcome: str
    source_timestamp: datetime | None = None
    received_at: datetime
    book_hash: str | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    midpoint: Decimal | None = None
    spread: Decimal | None = None
    last_trade_price: Decimal | None = None
    min_order_size: Decimal | None = None
    tick_size: Decimal | None = None
    neg_risk: bool | None = None
    bids: list[dict[str, Any]]
    asks: list[dict[str, Any]]


class CurrentMarketOrderbookResponse(BaseModel):
    market_id: int
    event_slug: str
    up: OrderbookSnapshotResponse
    down: OrderbookSnapshotResponse

