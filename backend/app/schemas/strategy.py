from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DecisionValue = Literal["BUY_UP", "BUY_DOWN", "NO_TRADE"]


class StrategyContext(BaseModel):
    strategy_name: str = "FINAL_3M_HIGHER_MARKET_PRICE"
    market_id: int
    event_slug: str
    up_token_id: str
    down_token_id: str
    time_remaining_seconds: int
    btc_start_price: Decimal | None = None
    btc_current_price: Decimal | None = None
    up_bid: Decimal | None = None
    up_ask: Decimal | None = None
    up_spread: Decimal | None = None
    down_bid: Decimal | None = None
    down_ask: Decimal | None = None
    down_spread: Decimal | None = None
    market_data_age_seconds: Decimal
    chainlink_data_age_seconds: Decimal | None = None
    paper_trading_enabled: bool = True
    trading_enabled: bool = False
    kill_switch_active: bool = False
    final_window_seconds: int = 180
    min_edge: Decimal = Decimal("0.05")
    max_spread: Decimal = Decimal("0.02")
    max_slippage: Decimal = Decimal("0.02")
    max_order_size_usd: Decimal = Decimal("10")
    max_daily_loss_usd: Decimal = Decimal("50")
    max_data_age_seconds: int = 5
    order_type: Literal["GTC", "FOK", "GTD", "FAK"] = "FAK"


class StrategyDecisionDTO(BaseModel):
    decision: DecisionValue
    outcome: Literal["UP", "DOWN"] | None = None
    mode: Literal["paper", "real"] = "paper"
    time_remaining_seconds: int
    btc_start_price: Decimal | None = None
    current_price: Decimal | None = None
    delta: Decimal | None = None
    up_bid: Decimal | None = None
    up_ask: Decimal | None = None
    down_bid: Decimal | None = None
    down_ask: Decimal | None = None
    estimated_probability: Decimal | None = None
    market_price: Decimal | None = None
    compared_up_value: Decimal | None = None
    compared_down_value: Decimal | None = None
    price_gap: Decimal | None = None
    edge: Decimal | None = None
    spread: Decimal | None = None
    risk_passed: bool = False
    risk_reasons: list[str] = Field(default_factory=list)
    reason: str
    raw_context: dict[str, Any]


class RiskResult(BaseModel):
    passed: bool
    reasons: list[str] = Field(default_factory=list)


class StrategyDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    market_id: int
    decision: str
    outcome: str | None
    mode: str
    time_remaining_seconds: int | None
    btc_start_price: Decimal | None
    current_price: Decimal | None
    delta: Decimal | None
    up_bid: Decimal | None
    up_ask: Decimal | None
    down_bid: Decimal | None
    down_ask: Decimal | None
    estimated_probability: Decimal | None
    market_price: Decimal | None
    edge: Decimal | None
    spread: Decimal | None
    risk_passed: bool
    risk_reasons: list[str]
    reason: str | None
    raw_context: dict[str, Any]
    created_at: datetime
