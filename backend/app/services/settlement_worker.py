from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market
from app.models.order import Order
from app.models.settlement import Settlement


class SettlementWorker:
    async def settle_market(
        self,
        session: AsyncSession,
        *,
        market: Market,
        winning_outcome: str,
        btc_end_price: Decimal | None = None,
        resolved_at: datetime | None = None,
    ) -> Settlement:
        result = await session.execute(select(Order).where(Order.market_id == market.id))
        orders = list(result.scalars().all())
        paper_pnl = _calculate_pnl(orders, winning_outcome, mode="paper")
        real_pnl = _calculate_pnl(orders, winning_outcome, mode="real")
        settlement = Settlement(
            market_id=market.id,
            winning_outcome=winning_outcome,
            btc_start_price=_decimal_or_none(market.raw_event.get("btc_start_price")),
            btc_end_price=btc_end_price,
            resolved_at=resolved_at or datetime.now().astimezone(),
            paper_pnl=paper_pnl,
            real_pnl=real_pnl,
            raw_resolution={"winning_outcome": winning_outcome},
        )
        session.add(settlement)
        await session.flush()
        await session.refresh(settlement)
        return settlement


def _calculate_pnl(orders: list[Order], winning_outcome: str, *, mode: str) -> Decimal:
    pnl = Decimal("0")
    for order in orders:
        if order.mode != mode:
            continue
        cost = order.price * order.size_matched
        payout = order.size_matched if order.outcome == winning_outcome else Decimal("0")
        pnl += payout - cost
    return pnl


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))

