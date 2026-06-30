from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.settings import StrategySettings
from app.services.settings import get_or_create_strategy_settings


BOT_STOPPED_RESULT = {"skipped": True, "reason": "BOT_STOPPED"}


async def is_bot_running(session: AsyncSession) -> bool:
    result = await session.execute(
        select(StrategySettings).where(StrategySettings.user_id.is_(None)).order_by(StrategySettings.id).limit(1)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        return True
    return bool(settings.bot_running)


async def set_bot_running(session: AsyncSession, running: bool) -> StrategySettings:
    settings = await get_or_create_strategy_settings(session)
    settings.bot_running = running
    session.add(settings)
    await session.flush()
    await session.refresh(settings)
    return settings
