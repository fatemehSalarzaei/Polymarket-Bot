from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RedeemEligibilityResponse(BaseModel):
    market_id: int
    condition_id: str
    winning_outcome: str | None
    eligible: bool
    status: str
    reasons: list[str] = Field(default_factory=list)
    real_winning_order_exists: bool = False
    matched_winning_size: Decimal | None = None


class RedeemRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    settlement_id: int | None
    condition_id: str
    winning_outcome: str
    status: str
    mode: str
    tx_hash: str | None
    wallet_address: str | None
    amount_redeemed: Decimal | None
    balance_before: Decimal | None
    balance_after: Decimal | None
    error_message: str | None
    raw_response: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RedeemAttemptResult(BaseModel):
    market_id: int
    condition_id: str
    winning_outcome: str
    status: str
    record: RedeemRecordResponse | None = None
    tx_hash: str | None = None
    amount_redeemed: Decimal | None = None
    balance_before: Decimal | None = None
    balance_after: Decimal | None = None
    error_message: str | None = None
    reasons: list[str] = Field(default_factory=list)


class RedeemStatusResponse(BaseModel):
    market_id: int
    condition_id: str
    winning_outcome: str | None
    status: str
    tx_hash: str | None = None
    amount_redeemed: Decimal | None = None
    balance_before: Decimal | None = None
    balance_after: Decimal | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    real_winning_order_exists: bool = False
    reasons: list[str] = Field(default_factory=list)
