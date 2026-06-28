from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.execution import GeoblockStatus
from app.schemas.wallet import WalletReadinessResponse


class TradingReadinessResponse(BaseModel):
    wallet: WalletReadinessResponse
    geoblock: GeoblockStatus
    paper_trading_enabled: bool
    trading_enabled: bool
    kill_switch_active: bool
    real_order_dry_run: bool
    trading_ready: bool
    blocking_reasons: list[str] = Field(default_factory=list)


class EnableTradingRequest(BaseModel):
    confirm_phrase: str


class TradingStatusResponse(BaseModel):
    trading_enabled: bool
    kill_switch_active: bool
    real_order_dry_run: bool
