from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.settlement import Settlement
from app.models.strategy import StrategyDecision
from app.schemas.pnl import PnlSummaryResponse


async def get_pnl_summary(session: AsyncSession) -> PnlSummaryResponse:
    paper_pnl = await session.scalar(select(func.coalesce(func.sum(Settlement.paper_pnl), 0)))
    real_pnl = await session.scalar(select(func.coalesce(func.sum(Settlement.real_pnl), 0)))
    settled_markets = await session.scalar(select(func.count(Settlement.id)))
    paper_orders = await session.scalar(select(func.count(Order.id)).where(Order.mode == "paper"))
    real_orders = await session.scalar(select(func.count(Order.id)).where(Order.mode == "real"))
    no_trade_count = await session.scalar(select(func.count(StrategyDecision.id)).where(StrategyDecision.decision == "NO_TRADE"))

    settlement_result = await session.execute(select(Settlement))
    settlements = list(settlement_result.scalars().all())
    winning_trades = sum(1 for settlement in settlements if (settlement.paper_pnl or 0) > 0 or (settlement.real_pnl or 0) > 0)
    losing_trades = sum(1 for settlement in settlements if (settlement.paper_pnl or 0) < 0 or (settlement.real_pnl or 0) < 0)
    total_resolved_trades = winning_trades + losing_trades
    win_rate = Decimal("0") if total_resolved_trades == 0 else Decimal(winning_trades) / Decimal(total_resolved_trades)

    return PnlSummaryResponse(
        paper_pnl=Decimal(str(paper_pnl or 0)),
        real_pnl=Decimal(str(real_pnl or 0)),
        paper_orders=int(paper_orders or 0),
        real_orders=int(real_orders or 0),
        settled_markets=int(settled_markets or 0),
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=win_rate,
        no_trade_count=int(no_trade_count or 0),
    )

