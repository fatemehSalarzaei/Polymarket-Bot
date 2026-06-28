from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.core.errors import error_payload
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.order import Order
from app.models.user import User
from app.schemas.execution import GeoblockStatus
from app.schemas.order import OrderResponse
from app.schemas.strategy import StrategyDecisionResponse
from app.services.dashboard_broadcaster import DashboardBroadcaster, dashboard_broadcaster
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.execution_engine import ExecutionEngine
from app.services.geoblock import GeoblockClient
from app.services.paper_trading import PaperTradingEngine
from app.services.polymarket_sdk import BackendOnlyClobSdkWrapper, build_clob_sdk_from_stored_wallet
from app.services.risk_manager import RiskManager
from app.services.settings import get_or_create_strategy_settings
from app.services.strategy_context_builder import StrategyContextBuilder
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.strategy.evaluate_current")
def evaluate_current_strategy_task() -> dict[str, Any]:
    return asyncio.run(evaluate_current_strategy_job())


@celery_app.task(name="app.tasks.strategy.evaluate_active_users")
def evaluate_active_users_task() -> dict[str, Any]:
    return asyncio.run(evaluate_active_users_job())


@celery_app.task(name="app.tasks.strategy.evaluate_current_for_user")
def evaluate_current_for_user_task(user_id: int) -> dict[str, Any]:
    return asyncio.run(evaluate_current_strategy_job(user_id=user_id))


async def evaluate_active_users_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    maker = sessionmaker or get_sessionmaker()
    async with maker() as session:
        result = await session.execute(select(User).where(User.is_active.is_(True)))
        users = list(result.scalars().all())
        processed: list[dict[str, Any]] = []
        for user in users:
            settings = await get_or_create_strategy_settings(session, user_id=user.id)
            if not (settings.paper_trading_enabled or settings.trading_enabled):
                continue
            processed.append(await evaluate_current_strategy_job(sessionmaker=maker, user_id=user.id))
        return {"processed": len(processed), "results": processed}


async def evaluate_current_strategy_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    builder: StrategyContextBuilder | None = None,
    broadcaster: DashboardBroadcaster = dashboard_broadcaster,
    user_id: int | None = None,
) -> dict[str, Any]:
    maker = sessionmaker or get_sessionmaker()
    async with maker() as session:
        build = await (builder or StrategyContextBuilder()).build(session, user_id=user_id)
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

        persisted = await persist_strategy_decision(session, market=build.market, decision=decision, user_id=user_id)
        strategy_event = StrategyDecisionResponse.model_validate(persisted)
        await broadcaster.broadcast("strategy_decision", strategy_event)
        await publish_dashboard_event("strategy_decision", strategy_event)

        order = None
        if risk.passed and await _has_no_paper_order(session, market_id=build.market.id, user_id=user_id):
            order = await PaperTradingEngine().create_order(
                session,
                market=build.market,
                persisted_decision=persisted,
                decision=decision,
                context=build.context,
                user_id=user_id,
            )
            if order is not None:
                order_event = OrderResponse.model_validate(order)
                await broadcaster.broadcast("order_update", order_event)
                await publish_dashboard_event("order_update", order_event)

        real_order = None
        if (
            decision.decision in {"BUY_UP", "BUY_DOWN"}
            and build.context.trading_enabled
            and await _has_no_real_order(session, market_id=build.market.id, user_id=user_id)
        ):
            try:
                geoblock_status = await GeoblockClient().get_status()
            except Exception as exc:
                logger.warning("real_order_geoblock_check_failed", extra={"exception_class": type(exc).__name__})
                geoblock_status = GeoblockStatus(blocked=True, checked=False, raw_response={"error": "GEOBLOCK_CHECK_FAILED"})
            try:
                sdk = await build_clob_sdk_from_stored_wallet(session, user_id=user_id)
            except Exception as exc:
                logger.warning("real_order_wallet_sdk_unavailable", extra={"exception_class": type(exc).__name__})
                sdk = BackendOnlyClobSdkWrapper(
                    credentials_configured=False,
                    wallet_configured=False,
                    api_credentials_configured=False,
                )
            real_result = await ExecutionEngine(sdk=sdk, dry_run=get_settings().real_order_dry_run).submit_real_order(
                session,
                market=build.market,
                persisted_decision=persisted,
                decision=decision,
                context=build.context,
                geoblock_status=geoblock_status,
                user_id=user_id,
            )
            if real_result.order_id is not None:
                result = await session.execute(select(Order).where(Order.id == real_result.order_id))
                real_order = result.scalar_one_or_none()
                if real_order is not None:
                    real_order_event = OrderResponse.model_validate(real_order)
                    await broadcaster.broadcast("order_update", real_order_event)
                    await publish_dashboard_event("order_update", real_order_event)

        await session.commit()
        return {
            "decision_id": persisted.id,
            "order_id": order.id if order is not None else None,
            "real_order_id": real_order.id if real_order is not None else None,
            "decision": persisted.decision,
        }


async def _has_no_paper_order(session: AsyncSession, *, market_id: int, user_id: int | None = None) -> bool:
    statement = select(Order.id).where(Order.market_id == market_id, Order.mode == "paper")
    if user_id is not None:
        statement = statement.where(Order.user_id == user_id)
    result = await session.execute(statement.limit(1))
    return result.scalar_one_or_none() is None


async def _has_no_real_order(session: AsyncSession, *, market_id: int, user_id: int | None = None) -> bool:
    statement = select(Order.id).where(Order.market_id == market_id, Order.mode == "real")
    if user_id is not None:
        statement = statement.where(Order.user_id == user_id)
    result = await session.execute(statement.limit(1))
    return result.scalar_one_or_none() is None
