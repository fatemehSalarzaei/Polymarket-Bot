from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.settings import StrategySettings
from app.core.config import get_settings
from app.schemas.settings import StrategySettingsPatch


async def get_or_create_strategy_settings(session: AsyncSession, *, user_id: int | None = None) -> StrategySettings:
    statement = select(StrategySettings)
    if user_id is not None:
        statement = statement.where(StrategySettings.user_id == user_id)
    else:
        statement = statement.where(StrategySettings.user_id.is_(None))
    result = await session.execute(statement.order_by(StrategySettings.id).limit(1))
    settings = result.scalar_one_or_none()
    if settings is not None:
        return settings

    app_settings = get_settings()
    settings = StrategySettings(
        user_id=user_id,
        final_window_seconds=app_settings.final_window_seconds,
        min_edge=Decimal(str(app_settings.min_edge)),
        max_spread=Decimal(str(app_settings.max_spread)),
        max_slippage=Decimal(str(app_settings.max_slippage)),
        max_order_size_usd=Decimal(str(app_settings.max_order_size_usd)),
        max_daily_loss_usd=Decimal(str(app_settings.max_daily_loss_usd)),
        max_data_age_seconds=app_settings.max_data_age_seconds,
        order_type=app_settings.default_order_type,
    )
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings


async def patch_strategy_settings(
    session: AsyncSession,
    settings: StrategySettings,
    patch: StrategySettingsPatch,
    *,
    actor: str,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    ip_address: str | None,
    user_agent: str | None,
) -> StrategySettings:
    updates = patch.model_dump(exclude_unset=True)
    before = serialize_strategy_settings(settings)

    for field, value in updates.items():
        setattr(settings, field, value)

    session.add(settings)
    await session.flush()
    await session.refresh(settings)

    audit_log = AuditLog(
        actor=actor,
        user_id=settings.user_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action="strategy_settings.patch",
        entity_type="strategy_settings",
        entity_id=str(settings.id),
        before=before,
        after=serialize_strategy_settings(settings),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(audit_log)
    await session.commit()
    await session.refresh(settings)
    return settings


def serialize_strategy_settings(settings: StrategySettings) -> dict[str, Any]:
    fields = [
        "id",
        "paper_trading_enabled",
        "trading_enabled",
        "bot_running",
        "kill_switch_active",
        "final_window_seconds",
        "min_edge",
        "max_spread",
        "max_slippage",
        "max_order_size_usd",
        "max_daily_loss_usd",
        "max_data_age_seconds",
        "order_type",
    ]
    return {field: _json_value(getattr(settings, field)) for field in fields}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value
