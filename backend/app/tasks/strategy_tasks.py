from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.core.errors import error_payload
from app.db.session import get_sessionmaker
from app.models.order import Order
from app.schemas.order import OrderResponse
from app.schemas.strategy import StrategyDecisionResponse
from app.services.dashboard_broadcaster import DashboardBroadcaster, dashboard_broadcaster
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.paper_trading import PaperTradingEngine
from app.services.risk_manager import RiskManager
from app.services.strategy_context_builder import StrategyContextBuilder
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.strategy.evaluate_current")
def evaluate_current_strategy_task() -> dict[str, Any]:
    return asyncio.run(evaluate_current_strategy_job())


async def evaluate_current_strategy_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    builder: StrategyContextBuilder | None = None,
    broadcaster: DashboardBroadcaster = dashboard_broadcaster,
) -> dict[str, Any]:
    maker = sessionmaker or get_sessionmaker()
    async with maker() as session:
        build = await (builder or StrategyContextBuilder()).build(session)
        if not build.ok:
            logger.warning("strategy_evaluation_skipped", extra={"missing": build.missing})
            detail = ", ".join(build.missing)
            await broadcaster.broadcast(
                "error",
                error_payload("STRATEGY_CONTEXT_INCOMPLETE", technical_detail=detail),
            )
            await publish_dashboard_event(
                "error",
                error_payload("STRATEGY_CONTEXT_INCOMPLETE", technical_detail=detail),
            )
            return {"decision_id": None, "order_id": None, "missing": build.missing}

        assert build.context is not None
        assert build.market is not None

        decision = await StrategyEngine().evaluate(build.context)
        risk = await RiskManager().validate_for_paper_trade(decision, build.context)
        decision.risk_passed = risk.passed
        decision.risk_reasons = risk.reasons

        persisted = await persist_strategy_decision(session, market=build.market, decision=decision)
        strategy_event = StrategyDecisionResponse.model_validate(persisted)
        await broadcaster.broadcast("strategy_decision", strategy_event)
        await publish_dashboard_event("strategy_decision", strategy_event)

        order = None
        if risk.passed and await _has_no_paper_order(session, market_id=build.market.id):
            order = await PaperTradingEngine().create_order(
                session,
                market=build.market,
                persisted_decision=persisted,
                decision=decision,
                context=build.context,
            )
            if order is not None:
                order_event = OrderResponse.model_validate(order)
                await broadcaster.broadcast("order_update", order_event)
                await publish_dashboard_event("order_update", order_event)

        await session.commit()
        return {
            "decision_id": persisted.id,
            "order_id": order.id if order is not None else None,
            "decision": persisted.decision,
        }


async def _has_no_paper_order(session: AsyncSession, *, market_id: int) -> bool:
    result = await session.execute(select(Order.id).where(Order.market_id == market_id, Order.mode == "paper").limit(1))
    return result.scalar_one_or_none() is None
