from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.bot import get_geoblock_client
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.trading import EnableTradingRequest, TradingReadinessResponse, TradingStatusResponse
from app.services.auth import get_current_user, user_id_or_none
from app.services.geoblock import GeoblockClient
from app.services.runtime_gate import is_bot_running
from app.services.settings import get_or_create_strategy_settings, serialize_strategy_settings
from app.services.wallet_credentials import clob_sdk_import_error, get_wallet_readiness

router = APIRouter()
CONFIRM_PHRASE = "ENABLE REAL TRADING"


@router.get("/trading/readiness", response_model=TradingReadinessResponse)
async def trading_readiness(
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
    geoblock_client: GeoblockClient = Depends(get_geoblock_client),
) -> TradingReadinessResponse:
    return await _readiness(session, current_user=current_user, geoblock_client=geoblock_client)


@router.get("/trading/status", response_model=TradingStatusResponse)
async def trading_status(
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> TradingStatusResponse:
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    return TradingStatusResponse(
        trading_enabled=settings.trading_enabled,
        kill_switch_active=settings.kill_switch_active,
        real_order_dry_run=get_settings().real_order_dry_run,
        mode=_trading_mode(),
    )


@router.post("/trading/enable", response_model=TradingStatusResponse)
async def enable_trading(
    payload: EnableTradingRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
    geoblock_client: GeoblockClient = Depends(get_geoblock_client),
) -> TradingStatusResponse:
    if payload.confirm_phrase != CONFIRM_PHRASE:
        raise AppError("REAL_TRADING_CONFIRMATION_INVALID", status_code=422)
    readiness = await _readiness(session, current_user=current_user, geoblock_client=geoblock_client)
    if not readiness.trading_ready:
        raise AppError("REAL_TRADING_NOT_READY", technical_detail=",".join(readiness.blocking_reasons), status_code=409)
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    before = serialize_strategy_settings(settings)
    settings.trading_enabled = True
    session.add(_audit(current_user, "trading.enable", before, serialize_strategy_settings(settings), request))
    await session.commit()
    return TradingStatusResponse(
        trading_enabled=True,
        kill_switch_active=settings.kill_switch_active,
        real_order_dry_run=get_settings().real_order_dry_run,
        mode=_trading_mode(),
    )


@router.post("/trading/disable", response_model=TradingStatusResponse)
async def disable_trading(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> TradingStatusResponse:
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    before = serialize_strategy_settings(settings)
    settings.trading_enabled = False
    session.add(_audit(current_user, "trading.disable", before, serialize_strategy_settings(settings), request))
    await session.commit()
    return TradingStatusResponse(
        trading_enabled=False,
        kill_switch_active=settings.kill_switch_active,
        real_order_dry_run=get_settings().real_order_dry_run,
        mode=_trading_mode(),
    )


@router.post("/trading/kill-switch/enable", response_model=TradingStatusResponse)
async def enable_kill_switch(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> TradingStatusResponse:
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    before = serialize_strategy_settings(settings)
    settings.kill_switch_active = True
    settings.trading_enabled = False
    session.add(_audit(current_user, "trading.kill_switch.enable", before, serialize_strategy_settings(settings), request))
    await session.commit()
    return TradingStatusResponse(
        trading_enabled=False,
        kill_switch_active=True,
        real_order_dry_run=get_settings().real_order_dry_run,
        mode=_trading_mode(),
    )


@router.post("/trading/kill-switch/disable", response_model=TradingStatusResponse)
async def disable_kill_switch(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> TradingStatusResponse:
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    before = serialize_strategy_settings(settings)
    settings.kill_switch_active = False
    session.add(_audit(current_user, "trading.kill_switch.disable", before, serialize_strategy_settings(settings), request))
    await session.commit()
    return TradingStatusResponse(
        trading_enabled=settings.trading_enabled,
        kill_switch_active=False,
        real_order_dry_run=get_settings().real_order_dry_run,
        mode=_trading_mode(),
    )


async def _readiness(
    session: AsyncSession,
    *,
    current_user: User | None,
    geoblock_client: GeoblockClient,
) -> TradingReadinessResponse:
    user_id = user_id_or_none(current_user)
    settings = await get_or_create_strategy_settings(session, user_id=user_id)
    wallet = await get_wallet_readiness(session, user_id=user_id)
    bot_running = await is_bot_running(session)
    current_mode_reasons = list(wallet.blocking_reasons)
    real_reasons = list(wallet.blocking_reasons)
    warnings: list[str] = []
    config = get_settings()
    sdk_import_error = clob_sdk_import_error()
    wallet_redeem_flow_blocking_reason = _wallet_redeem_flow_blocking_reason(wallet)
    wallet_redeem_flow_supported = wallet_redeem_flow_blocking_reason is None
    if sdk_import_error is not None:
        current_mode_reasons.append(sdk_import_error)
        real_reasons.append(sdk_import_error)
    if not bot_running:
        current_mode_reasons.append("BOT_STOPPED")
        real_reasons.append("BOT_STOPPED")
    try:
        geoblock = await geoblock_client.get_status()
    except Exception:
        from app.schemas.execution import GeoblockStatus

        geoblock = GeoblockStatus(blocked=True, checked=False, raw_response={"error": "GEOBLOCK_CHECK_FAILED"})
        if config.real_order_dry_run:
            warnings.append("GEOBLOCK_CHECK_FAILED")
        else:
            current_mode_reasons.append("GEOBLOCK_CHECK_FAILED")
        real_reasons.append("GEOBLOCK_CHECK_FAILED")
    if geoblock.blocked and geoblock.checked:
        if config.real_order_dry_run:
            warnings.append("GEOBLOCK_BLOCKED")
        else:
            current_mode_reasons.append("GEOBLOCK_BLOCKED")
        real_reasons.append("GEOBLOCK_BLOCKED")
    if settings.kill_switch_active:
        current_mode_reasons.append("KILL_SWITCH_ACTIVE")
        real_reasons.append("KILL_SWITCH_ACTIVE")
    if not config.polygon_rpc_url:
        real_reasons.append("POLYGON_RPC_URL_MISSING")
    if not config.resolved_collateral_token_address:
        real_reasons.append("COLLATERAL_TOKEN_MISSING")
    if not config.conditional_tokens_contract_address:
        real_reasons.append("CONDITIONAL_TOKENS_CONTRACT_MISSING")
    if not wallet_redeem_flow_supported and wallet_redeem_flow_blocking_reason:
        real_reasons.append(wallet_redeem_flow_blocking_reason)
    if not config.real_order_dry_run and (not config.trading_enabled or not config.real_trading_confirmation_enabled):
        current_mode_reasons.append("REAL_TRADING_ENV_DISABLED")
        real_reasons.append("REAL_TRADING_ENV_DISABLED")
    if config.real_order_dry_run:
        real_reasons.append("REAL_ORDER_DRY_RUN_ACTIVE")
    elif not (config.trading_enabled and config.real_trading_confirmation_enabled):
        real_reasons.append("REAL_TRADING_ENV_DISABLED")
    current_mode_reasons = list(dict.fromkeys(current_mode_reasons))
    real_reasons = list(dict.fromkeys(real_reasons))
    warnings = list(dict.fromkeys(warnings))
    paper_trading_ready = bot_running and not settings.kill_switch_active
    dry_run_trading_ready = wallet.trading_ready and bot_running and not settings.kill_switch_active
    real_trading_ready = not real_reasons
    real_trading_available = not config.real_order_dry_run and real_trading_ready
    return TradingReadinessResponse(
        wallet=wallet,
        geoblock=geoblock,
        paper_trading_enabled=settings.paper_trading_enabled,
        bot_running=bot_running,
        user_trading_enabled=settings.trading_enabled,
        env_trading_enabled=config.trading_enabled,
        real_trading_confirmation_enabled=config.real_trading_confirmation_enabled,
        redeem_enabled=config.redeem_enabled,
        redeem_dry_run=config.redeem_dry_run,
        trading_enabled=settings.trading_enabled,
        kill_switch_active=settings.kill_switch_active,
        real_order_dry_run=config.real_order_dry_run,
        wallet_configured=wallet.wallet_configured,
        api_credentials_configured=wallet.api_credentials_configured,
        sdk_import_ok=sdk_import_error is None,
        polygon_rpc_configured=bool(config.polygon_rpc_url),
        collateral_token_configured=bool(config.resolved_collateral_token_address),
        conditional_tokens_contract_configured=bool(config.conditional_tokens_contract_address),
        wallet_redeem_flow_supported=wallet_redeem_flow_supported,
        wallet_redeem_flow_status=wallet.redeem_flow_status,
        wallet_redeem_flow_blocking_reason=wallet_redeem_flow_blocking_reason,
        official_resolution_client_available=bool(config.polymarket_gamma_host),
        trading_ready=not current_mode_reasons,
        paper_trading_ready=paper_trading_ready,
        dry_run_trading_ready=dry_run_trading_ready,
        real_trading_ready=real_trading_ready,
        real_trading_available=real_trading_available,
        blocking_reasons=current_mode_reasons,
        real_trading_blocking_reasons=real_reasons,
        warnings=warnings,
    )


def _trading_mode() -> str:
    return "dry_run" if get_settings().real_order_dry_run else "real"


def _wallet_redeem_flow_blocking_reason(wallet) -> str | None:
    if (
        wallet.funder_address_configured
        and wallet.wallet_address
        and getattr(wallet, "funder_address", None)
        and wallet.funder_address.lower() != wallet.wallet_address.lower()
    ):
        return "PROXY_WALLET_REDEEM_REQUIRES_RELAYER"
    return None


def _audit(user: User | None, action: str, before: dict, after: dict, request: Request) -> AuditLog:
    return AuditLog(
        user_id=user_id_or_none(user),
        actor_user_id=user_id_or_none(user),
        actor_role=user.role if user is not None else None,
        actor=user.username if user is not None else "dashboard",
        action=action,
        entity_type="strategy_settings",
        entity_id=str(after.get("id")),
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
