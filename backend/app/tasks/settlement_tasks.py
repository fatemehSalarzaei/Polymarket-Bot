from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.services.dashboard_broadcaster import DashboardBroadcaster, dashboard_broadcaster
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.pnl import get_pnl_summary
from app.services.settlement_worker import SettlementWorker


@celery_app.task(name="app.tasks.settlement.settle_finished_markets")
def settle_finished_markets_task() -> dict[str, Any]:
    return asyncio.run(settle_finished_markets_job())


async def settle_finished_markets_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    broadcaster: DashboardBroadcaster = dashboard_broadcaster,
) -> dict[str, Any]:
    maker = sessionmaker or get_sessionmaker()
    async with maker() as session:
        settlements = await SettlementWorker().settle_finished_markets(session)
        await session.commit()
        if settlements:
            summary = await get_pnl_summary(session)
            await broadcaster.broadcast("pnl_summary", summary)
            await publish_dashboard_event("pnl_summary", summary)
        return {"settled": len(settlements), "market_ids": [settlement.market_id for settlement in settlements]}
