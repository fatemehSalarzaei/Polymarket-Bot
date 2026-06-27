from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ActiveMarketDTO(BaseModel):
    event_slug: str
    market_slug: str | None = None
    condition_id: str
    question: str | None = None
    active: bool
    closed: bool
    start_ts: int | None = None
    end_ts: int | None = None
    up_token_id: str
    down_token_id: str
    raw_event: dict[str, Any]
    raw_market: dict[str, Any]


class MarketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_slug: str
    market_slug: str | None = None
    condition_id: str
    question: str | None = None
    active: bool
    closed: bool
    start_ts: int | None = None
    end_ts: int | None = None
    up_token_id: str
    down_token_id: str
    created_at: datetime
    updated_at: datetime

