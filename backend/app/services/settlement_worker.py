import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settlement import Settlement
from app.models.tick import ChainlinkTick


logger = logging.getLogger(__name__)


class SettlementWorker:
    async def settle_finished_markets(self, session: AsyncSession, *, now: datetime | None = None) -> list[Settlement]:
        current_time = now or datetime.now(UTC)
        current_ts = int(current_time.timestamp())
        result = await session.execute(
            select(Market)
            .where(Market.end_ts.is_not(None), Market.end_ts <= current_ts)
            .where(~Market.settlements.any())
        )
        markets = list(result.scalars().all())
        settlements: list[Settlement] = []

        for market in markets:
            start_tick = await _nearest_tick(session, market.start_ts)
            end_tick = await _nearest_tick(session, market.end_ts)
            if start_tick is None or end_tick is None:
                logger.warning(
                    "settlement_skipped",
                    extra={"market_id": market.id, "reason": "CHAINLINK_TICKS_MISSING"},
                )
                continue

            winning_outcome = "UP" if end_tick.value >= start_tick.value else "DOWN"
            settlement = await self.settle_market(
                session,
                market=market,
                winning_outcome=winning_outcome,
                btc_start_price=start_tick.value,
                btc_end_price=end_tick.value,
                resolved_at=current_time,
            )
            settlements.append(settlement)

        return settlements

    async def settle_market(
        self,
        session: AsyncSession,
        *,
        market: Market,
        winning_outcome: str,
        user_id: int | None = None,
        btc_start_price: Decimal | None = None,
        btc_end_price: Decimal | None = None,
        resolved_at: datetime | None = None,
    ) -> Settlement:
        statement = select(Order).where(Order.market_id == market.id)
        if user_id is not None:
            statement = statement.where(Order.user_id == user_id)
        result = await session.execute(statement)
        orders = list(result.scalars().all())
        paper_pnl = _calculate_pnl(orders, winning_outcome, mode="paper")
        real_pnl = _calculate_pnl(orders, winning_outcome, mode="real")
        settlement = Settlement(
            user_id=user_id,
            market_id=market.id,
            winning_outcome=winning_outcome,
            btc_start_price=btc_start_price or _decimal_or_none(market.raw_event.get("btc_start_price")),
            btc_end_price=btc_end_price,
            resolved_at=resolved_at or datetime.now(UTC),
            paper_pnl=paper_pnl,
            real_pnl=real_pnl,
            raw_resolution={"winning_outcome": winning_outcome},
        )
        session.add(settlement)
        await session.flush()
        await session.refresh(settlement)
        await _create_redeem_record_if_ready(session, market=market, settlement=settlement, orders=orders, user_id=user_id)
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


async def _create_redeem_record_if_ready(
    session: AsyncSession,
    *,
    market: Market,
    settlement: Settlement,
    orders: list[Order],
    user_id: int | None,
) -> None:
    winning_real_orders = [
        order
        for order in orders
        if order.mode == "real" and order.outcome == settlement.winning_outcome and order.size_matched > 0
    ]
    if not winning_real_orders or not market.condition_id:
        return
    statement = select(RedeemRecord.id).where(
        RedeemRecord.market_id == market.id,
        RedeemRecord.condition_id == market.condition_id,
        RedeemRecord.mode == "real",
    )
    if user_id is not None:
        statement = statement.where(RedeemRecord.user_id == user_id)
    existing = await session.execute(statement.limit(1))
    if existing.scalar_one_or_none() is not None:
        return
    session.add(
        RedeemRecord(
            user_id=user_id,
            wallet_credential_id=winning_real_orders[0].wallet_credential_id,
            market_id=market.id,
            settlement_id=settlement.id,
            condition_id=market.condition_id,
            winning_outcome=settlement.winning_outcome,
            status="READY_TO_REDEEM",
            mode="real",
            raw_request={},
            raw_response={"created_by": "settlement_worker"},
        )
    )


def _decimal_or_none(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


async def _nearest_tick(session: AsyncSession, unix_ts: int | None) -> ChainlinkTick | None:
    if unix_ts is None:
        return None
    target = datetime.fromtimestamp(unix_ts, tz=UTC)
    result = await session.execute(select(ChainlinkTick))
    ticks = list(result.scalars().all())
    if not ticks:
        return None
    return min(ticks, key=lambda tick: abs((_tick_time(tick) - target).total_seconds()))


def _tick_time(tick: ChainlinkTick) -> datetime:
    value = tick.source_timestamp or tick.received_at
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
