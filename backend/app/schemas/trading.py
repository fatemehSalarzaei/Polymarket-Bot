from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.execution import GeoblockStatus
from app.schemas.wallet import WalletReadinessResponse


class TradingReadinessResponse(BaseModel):
    wallet: WalletReadinessResponse
    geoblock: GeoblockStatus
    paper_trading_enabled: bool
    bot_running: bool
    user_trading_enabled: bool
    env_trading_enabled: bool
    real_trading_confirmation_enabled: bool
    redeem_enabled: bool
    redeem_dry_run: bool
    trading_enabled: bool
    kill_switch_active: bool
    real_order_dry_run: bool
    wallet_configured: bool
    api_credentials_configured: bool
    sdk_import_ok: bool
    polygon_rpc_configured: bool
    collateral_token_configured: bool
    conditional_tokens_contract_configured: bool
    wallet_redeem_flow_supported: bool
    wallet_redeem_flow_blocking_reason: str | None = None
    official_resolution_client_available: bool
    trading_ready: bool
    paper_trading_ready: bool
    dry_run_trading_ready: bool
    real_trading_ready: bool
    real_trading_available: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    real_trading_blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EnableTradingRequest(BaseModel):
    confirm_phrase: str


class TradingStatusResponse(BaseModel):
    trading_enabled: bool
    kill_switch_active: bool
    real_order_dry_run: bool
    mode: str
