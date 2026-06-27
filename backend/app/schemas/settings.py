from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class StrategySettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_trading_enabled: bool
    trading_enabled: bool
    kill_switch_active: bool
    final_window_seconds: int
    min_edge: Decimal
    max_spread: Decimal
    max_slippage: Decimal
    max_order_size_usd: Decimal
    max_daily_loss_usd: Decimal
    max_data_age_seconds: int
    order_type: str
    updated_at: datetime


class StrategySettingsPatch(BaseModel):
    paper_trading_enabled: bool | None = None
    trading_enabled: bool | None = None
    kill_switch_active: bool | None = None
    final_window_seconds: int | None = Field(default=None, ge=1, le=900)
    min_edge: Decimal | None = Field(default=None, ge=0, le=1)
    max_spread: Decimal | None = Field(default=None, ge=0, le=1)
    max_slippage: Decimal | None = Field(default=None, ge=0, le=1)
    max_order_size_usd: Decimal | None = Field(default=None, gt=0)
    max_daily_loss_usd: Decimal | None = Field(default=None, gt=0)
    max_data_age_seconds: int | None = Field(default=None, ge=1, le=300)
    order_type: str | None = Field(default=None, pattern="^(GTC|FOK|GTD|FAK)$")

