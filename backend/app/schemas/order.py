from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    strategy_decision_id: int | None
    mode: str
    external_order_id: str | None
    token_id: str
    outcome: str
    side: str
    order_type: str
    price: Decimal
    size: Decimal
    size_matched: Decimal
    status: str
    submitted_at: datetime
    updated_at: datetime
    filled_at: datetime | None
    raw_response: dict[str, Any]
    error_message: str | None

