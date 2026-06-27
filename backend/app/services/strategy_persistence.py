import logging

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market
from app.models.order import Order
from app.models.strategy import StrategyDecision
from app.schemas.strategy import StrategyDecisionDTO

logger = logging.getLogger(__name__)


async def persist_strategy_decision(
    session: AsyncSession,
    *,
    market: Market,
    decision: StrategyDecisionDTO,
) -> StrategyDecision:
    row = StrategyDecision(
        market_id=market.id,
        decision=decision.decision,
        outcome=decision.outcome,
        mode=decision.mode,
        time_remaining_seconds=decision.time_remaining_seconds,
        btc_start_price=decision.btc_start_price,
        current_price=decision.current_price,
        delta=decision.delta,
        up_bid=decision.up_bid,
        up_ask=decision.up_ask,
        down_bid=decision.down_bid,
        down_ask=decision.down_ask,
        estimated_probability=decision.estimated_probability,
        market_price=decision.market_price,
        edge=decision.edge,
        spread=decision.spread,
        risk_passed=decision.risk_passed,
        risk_reasons=decision.risk_reasons,
        reason=decision.reason,
        raw_context=decision.raw_context,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    logger.info(
        "strategy_decision_persisted",
        extra={
            "decision": row.decision,
            "market_id": row.market_id,
            "edge": str(row.edge) if row.edge is not None else None,
            "risk_passed": row.risk_passed,
            "reason": row.reason,
        },
    )
    return row


async def get_latest_decision(session: AsyncSession) -> StrategyDecision | None:
    result = await session.execute(select(StrategyDecision).order_by(desc(StrategyDecision.created_at), desc(StrategyDecision.id)).limit(1))
    return result.scalar_one_or_none()


async def list_decisions(session: AsyncSession, *, limit: int = 100) -> list[StrategyDecision]:
    result = await session.execute(
        select(StrategyDecision).order_by(desc(StrategyDecision.created_at), desc(StrategyDecision.id)).limit(limit)
    )
    return list(result.scalars().all())


async def list_orders(session: AsyncSession, *, limit: int = 100) -> list[Order]:
    result = await session.execute(select(Order).order_by(desc(Order.submitted_at), desc(Order.id)).limit(limit))
    return list(result.scalars().all())
