from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market
from app.models.tick import ChainlinkTick, OrderbookSnapshot
from app.schemas.strategy import StrategyContext
from app.core.config import get_settings
from app.services.settings import get_or_create_strategy_settings


@dataclass
class StrategyContextBuildResult:
    context: StrategyContext | None
    market: Market | None
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.context is not None and self.market is not None and not self.missing


class StrategyContextBuilder:
    def __init__(self, *, start_tick_tolerance_seconds: int | None = None) -> None:
        settings = get_settings()
        self._start_tick_tolerance_seconds = start_tick_tolerance_seconds or settings.chainlink_start_tick_tolerance_seconds

    async def build(self, session: AsyncSession, *, now: datetime | None = None) -> StrategyContextBuildResult:
        current_time = _ensure_aware(now or datetime.now(UTC))
        market = await self._current_market(session, current_time)
        if market is None:
            return StrategyContextBuildResult(context=None, market=None, missing=["CURRENT_MARKET_MISSING"])

        up_snapshot = await self._latest_snapshot(session, market=market, outcome="UP")
        down_snapshot = await self._latest_snapshot(session, market=market, outcome="DOWN")
        latest_tick = await self._latest_tick(session)
        start_tick = await self._nearest_tick(
            session,
            market.start_ts,
            tolerance_seconds=self._start_tick_tolerance_seconds,
        )

        missing: list[str] = []
        if up_snapshot is None:
            missing.append("UP_ORDERBOOK_MISSING")
        if down_snapshot is None:
            missing.append("DOWN_ORDERBOOK_MISSING")
        if missing:
            return StrategyContextBuildResult(context=None, market=market, missing=missing)

        assert up_snapshot is not None
        assert down_snapshot is not None

        settings = await get_or_create_strategy_settings(session)
        end_ts = market.end_ts or ((market.start_ts or int(current_time.timestamp())) + 900)
        market_received_at = max(_ensure_aware(up_snapshot.received_at), _ensure_aware(down_snapshot.received_at))

        context = StrategyContext(
            strategy_name="FINAL_3M_HIGHER_MARKET_PRICE",
            market_id=market.id,
            event_slug=market.event_slug,
            up_token_id=market.up_token_id,
            down_token_id=market.down_token_id,
            time_remaining_seconds=max(0, end_ts - int(current_time.timestamp())),
            btc_start_price=start_tick.value if start_tick is not None else None,
            btc_current_price=latest_tick.value if latest_tick is not None else None,
            up_bid=up_snapshot.best_bid,
            up_ask=up_snapshot.best_ask,
            up_spread=up_snapshot.spread,
            down_bid=down_snapshot.best_bid,
            down_ask=down_snapshot.best_ask,
            down_spread=down_snapshot.spread,
            market_data_age_seconds=_age_seconds(current_time, market_received_at),
            chainlink_data_age_seconds=(
                _age_seconds(current_time, _ensure_aware(latest_tick.received_at)) if latest_tick is not None else None
            ),
            paper_trading_enabled=settings.paper_trading_enabled,
            trading_enabled=settings.trading_enabled,
            kill_switch_active=settings.kill_switch_active,
            final_window_seconds=settings.final_window_seconds,
            min_edge=settings.min_edge,
            max_spread=settings.max_spread,
            max_slippage=settings.max_slippage,
            max_order_size_usd=settings.max_order_size_usd,
            max_daily_loss_usd=settings.max_daily_loss_usd,
            max_data_age_seconds=settings.max_data_age_seconds,
            order_type=settings.order_type,
        )
        return StrategyContextBuildResult(context=context, market=market)

    async def _current_market(self, session: AsyncSession, now: datetime) -> Market | None:
        now_ts = int(now.timestamp())
        result = await session.execute(
            select(Market)
            .where(Market.active.is_(True), Market.closed.is_(False))
            .where((Market.end_ts.is_(None)) | (Market.end_ts >= now_ts - 60))
            .order_by(desc(Market.start_ts), desc(Market.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_snapshot(
        self,
        session: AsyncSession,
        *,
        market: Market,
        outcome: str,
    ) -> OrderbookSnapshot | None:
        result = await session.execute(
            select(OrderbookSnapshot)
            .where(OrderbookSnapshot.market_id == market.id, OrderbookSnapshot.outcome == outcome)
            .order_by(desc(OrderbookSnapshot.received_at), desc(OrderbookSnapshot.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_tick(self, session: AsyncSession) -> ChainlinkTick | None:
        result = await session.execute(select(ChainlinkTick).order_by(desc(ChainlinkTick.received_at), desc(ChainlinkTick.id)).limit(1))
        return result.scalar_one_or_none()

    async def _nearest_tick(
        self,
        session: AsyncSession,
        unix_ts: int | None,
        *,
        tolerance_seconds: int | None = None,
    ) -> ChainlinkTick | None:
        if unix_ts is None:
            return await self._latest_tick(session)
        target = datetime.fromtimestamp(unix_ts, tz=UTC)
        result = await session.execute(select(ChainlinkTick))
        ticks = list(result.scalars().all())
        if not ticks:
            return None
        nearest = min(ticks, key=lambda tick: abs((_tick_time(tick) - target).total_seconds()))
        if tolerance_seconds is not None:
            age = abs((_tick_time(nearest) - target).total_seconds())
            if age > tolerance_seconds:
                return None
        return nearest


def _tick_time(tick: ChainlinkTick) -> datetime:
    return _ensure_aware(tick.source_timestamp or tick.received_at)


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _age_seconds(now: datetime, timestamp: datetime) -> Decimal:
    return Decimal(str(max(0.0, (now - timestamp).total_seconds())))
