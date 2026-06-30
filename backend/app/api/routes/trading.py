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
    current_mode_reasons = list(wallet.blocking_reasons)
    real_reasons = list(wallet.blocking_reasons)
    warnings: list[str] = []
    config = get_settings()
    sdk_import_error = clob_sdk_import_error()
    if sdk_import_error is not None:
        current_mode_reasons.append(sdk_import_error)
        real_reasons.append(sdk_import_error)
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
    paper_trading_ready = not settings.kill_switch_active
    dry_run_trading_ready = wallet.trading_ready and not settings.kill_switch_active
    real_trading_ready = not real_reasons
    real_trading_available = not config.real_order_dry_run and real_trading_ready
    return TradingReadinessResponse(
        wallet=wallet,
        geoblock=geoblock,
        paper_trading_enabled=settings.paper_trading_enabled,
        trading_enabled=settings.trading_enabled,
        kill_switch_active=settings.kill_switch_active,
        real_order_dry_run=config.real_order_dry_run,
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
