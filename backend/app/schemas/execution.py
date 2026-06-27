from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class PlaceOrderRequest(BaseModel):
    token_id: str
    side: Literal["BUY", "SELL"] = "BUY"
    price: Decimal
    size: Decimal
    order_type: Literal["GTC", "FOK", "GTD", "FAK"] = "FAK"


class PlaceOrderResult(BaseModel):
    submitted: bool
    dry_run: bool = False
    external_order_id: str | None = None
    status: str
    raw_response: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class GeoblockStatus(BaseModel):
    blocked: bool
    raw_response: dict[str, Any] = Field(default_factory=dict)
    checked: bool = True


class RealOrderResult(BaseModel):
    submitted: bool
    dry_run: bool
    status: str
    order_id: int | None = None
    external_order_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    raw_response: dict[str, Any] = Field(default_factory=dict)

