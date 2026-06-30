from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settlement import Settlement
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.order_lifecycle import is_real_order_reconciled_with_match
from app.services.redeem_service import RedeemService
from app.services.runtime_gate import BOT_STOPPED_RESULT, is_bot_running


@celery_app.task(name="app.tasks.redeem.redeem_resolved_winning_positions")
def redeem_resolved_winning_positions_task() -> dict[str, Any]:
    return asyncio.run(redeem_resolved_winning_positions_job())


async def redeem_resolved_winning_positions_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    service: RedeemService | None = None,
) -> dict[str, Any]:
    maker = sessionmaker or get_sessionmaker()
    redeem_service = service or RedeemService()
    processed: list[dict[str, Any]] = []

    async with maker() as session:
        if not await is_bot_running(session):
            return dict(BOT_STOPPED_RESULT)
        candidates = await _candidate_settlements(session)
        for settlement, market, user_id in candidates:
            eligibility = await redeem_service.check_redeem_eligibility(session, market, settlement, user_id=user_id)
            if not eligibility.eligible:
                continue
            result = await redeem_service.redeem_winning_position(session, market, settlement, user_id=user_id)
            await session.commit()
            payload = result.model_dump(mode="json")
            await publish_dashboard_event("redeem_update", payload)
            processed.append(payload)

    return {"processed": len(processed), "redeems": processed}


async def _candidate_settlements(session: AsyncSession) -> list[tuple[Settlement, Market, int | None]]:
    result = await session.execute(
        select(Settlement, Market)
        .join(Market, Market.id == Settlement.market_id)
    )
    rows = list(result.all())
    candidates: list[tuple[Settlement, Market, int | None]] = []
    for settlement, market in rows:
        user_ids = await _users_with_winning_real_order(
            session,
            market_id=market.id,
            winning_outcome=settlement.winning_outcome,
        )
        for user_id in user_ids:
            if await _has_confirmed_redeem(session, market=market, user_id=user_id):
                continue
            candidates.append((settlement, market, user_id))
    return candidates


async def _users_with_winning_real_order(session: AsyncSession, *, market_id: int, winning_outcome: str) -> list[int | None]:
    result = await session.execute(
        select(Order.user_id)
        .where(
            Order.market_id == market_id,
            Order.mode == "real",
            Order.outcome == winning_outcome,
        )
        .distinct()
    )
    user_ids: list[int | None] = []
    for user_id in result.scalars().all():
        order_result = await session.execute(
            select(Order).where(
                Order.market_id == market_id,
                Order.mode == "real",
                Order.outcome == winning_outcome,
                Order.user_id.is_(None) if user_id is None else Order.user_id == user_id,
            )
        )
        if any(is_real_order_reconciled_with_match(order) for order in order_result.scalars().all()):
            user_ids.append(user_id)
    return user_ids


async def _has_confirmed_redeem(session: AsyncSession, *, market: Market, user_id: int | None) -> bool:
    statement = select(RedeemRecord.id).where(
        RedeemRecord.market_id == market.id,
        RedeemRecord.condition_id == market.condition_id,
        RedeemRecord.mode == "real",
        RedeemRecord.status == "REDEEM_CONFIRMED",
    )
    if user_id is None:
        statement = statement.where(RedeemRecord.user_id.is_(None))
    else:
        statement = statement.where(RedeemRecord.user_id == user_id)
    result = await session.execute(statement.limit(1))
    return result.scalar_one_or_none() is not None
