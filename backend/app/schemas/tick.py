from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChainlinkTickResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    value: Decimal
    source: str
    source_timestamp: datetime | None
    received_at: datetime
    raw_payload: dict[str, Any]

