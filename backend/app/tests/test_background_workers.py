from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.audit import AuditLog
from app.models.market import Market
from app.models.order import Order
from app.models.settlement import Settlement
from app.models.strategy import StrategyDecision
from app.models.tick import ChainlinkTick, OrderbookSnapshot
from app.services.strategy_context_builder import StrategyContextBuilder
from app.tasks.settlement_tasks import settle_finished_markets_job
from app.tasks.strategy_tasks import evaluate_current_strategy_job
from app.tasks.market_tasks import fetch_current_orderbook_job
from app.services.polymarket_errors import PolymarketHttpError


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest.fixture()
def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[TestClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_celery_app_config_loads_without_broker_connection() -> None:
    assert celery_app.main == "polymarket_bot"
    assert "app.tasks.strategy.evaluate_current" in celery_app.tasks
    assert celery_app.conf.beat_schedule["evaluate-current-strategy"]["schedule"] == 5.0
    assert celery_app.conf.beat_schedule["fetch-current-orderbook"]["schedule"] == 15.0


@pytest.mark.asyncio
async def test_strategy_context_builder_returns_missing_data_safely(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        market = _market("missing", start_delta_seconds=-780, end_delta_seconds=120)
        session.add(market)
        await session.commit()

        result = await StrategyContextBuilder().build(session)

    assert result.context is None
    assert result.market is not None
    assert set(result.missing) == {
        "UP_ORDERBOOK_MISSING",
        "DOWN_ORDERBOOK_MISSING",
    }


@pytest.mark.asyncio
async def test_strategy_task_creates_only_one_paper_order_per_market(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        market = _market("strategy", start_delta_seconds=-780, end_delta_seconds=120)
        session.add(market)
        await session.flush()
        await _seed_strategy_inputs(session, market)
        await session.commit()

    first = await evaluate_current_strategy_job(sessionmaker=sessionmaker)
    second = await evaluate_current_strategy_job(sessionmaker=sessionmaker)

    async with sessionmaker() as session:
        decisions = list((await session.execute(select(StrategyDecision))).scalars().all())
        orders = list((await session.execute(select(Order))).scalars().all())

    assert first["order_id"] is not None
    assert second["order_id"] is None
    assert len(decisions) == 2
    assert len(orders) == 1
    assert orders[0].mode == "paper"
    assert orders[0].outcome == "UP"


@pytest.mark.asyncio
async def test_strategy_context_builder_does_not_require_chainlink_ticks(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        market = _market("no-chainlink", start_delta_seconds=-780, end_delta_seconds=120)
        session.add(market)
        await session.flush()
        await _seed_orderbooks(session, market)
        await session.commit()

        result = await StrategyContextBuilder().build(session)

    assert result.ok
    assert result.context is not None
    assert result.context.btc_start_price is None
    assert result.context.btc_current_price is None
    assert result.context.up_ask == Decimal("0.90")
    assert result.context.down_ask == Decimal("0.11")


@pytest.mark.asyncio
async def test_orderbook_task_catches_polymarket_timeout(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        market = _market("task-timeout", start_delta_seconds=-780, end_delta_seconds=120)
        session.add(market)
        await session.commit()

    result = await fetch_current_orderbook_job(sessionmaker=sessionmaker, clob_client=TimeoutClobClient())

    assert result == {"persisted": 0, "reason": "POLYMARKET_CLOB_TIMEOUT", "recoverable": True}


@pytest.mark.asyncio
async def test_settlement_task_calculates_up_and_down_pnl(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        up_market = _market("settle-up", start_delta_seconds=-1000, end_delta_seconds=-100)
        down_market = _market("settle-down", start_delta_seconds=-2000, end_delta_seconds=-1100)
        session.add_all([up_market, down_market])
        await session.flush()

        await _seed_order(session, up_market, outcome="UP", price=Decimal("0.40"), size=Decimal("10"))
        await _seed_order(session, down_market, outcome="UP", price=Decimal("0.40"), size=Decimal("10"))
        await _seed_ticks(session, up_market, start_price=Decimal("100"), end_price=Decimal("101"))
        await _seed_ticks(session, down_market, start_price=Decimal("100"), end_price=Decimal("99"))
        await session.commit()

    result = await settle_finished_markets_job(sessionmaker=sessionmaker)

    async with sessionmaker() as session:
        settlements = list((await session.execute(select(Settlement).order_by(Settlement.market_id))).scalars().all())

    assert result["settled"] == 2
    assert settlements[0].winning_outcome == "UP"
    assert settlements[0].paper_pnl == Decimal("6.00000000")
    assert settlements[1].winning_outcome == "DOWN"
    assert settlements[1].paper_pnl == Decimal("-4.00000000")


def test_bot_start_records_state_without_spawning_loops(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    response = client.post("/api/bot/start")

    async def read_logs() -> list[AuditLog]:
        async with sessionmaker() as session:
            return list((await session.execute(select(AuditLog))).scalars().all())

    logs = asyncio.run(read_logs())

    assert response.status_code == 200
    assert response.json()["running"] is True
    assert response.json()["background_workers_required"] is True
    assert "celery_worker" in response.json()["message"]
    assert [log.action for log in logs] == ["bot.start"]
    client.post("/api/bot/stop")


def _market(slug_suffix: str, *, start_delta_seconds: int, end_delta_seconds: int) -> Market:
    now_ts = int(datetime.now(UTC).timestamp())
    start_ts = now_ts + start_delta_seconds
    end_ts = now_ts + end_delta_seconds
    return Market(
        event_slug=f"btc-updown-15m-{slug_suffix}",
        market_slug=f"btc-updown-15m-{slug_suffix}-market",
        condition_id=f"condition-{slug_suffix}",
        question="BTC Up or Down",
        active=True,
        closed=False,
        start_ts=start_ts,
        end_ts=end_ts,
        up_token_id=f"up-token-{slug_suffix}",
        down_token_id=f"down-token-{slug_suffix}",
        raw_event={},
        raw_market={},
    )


async def _seed_strategy_inputs(session: AsyncSession, market: Market) -> None:
    now = datetime.now(UTC)
    start_time = datetime.fromtimestamp(market.start_ts, tz=UTC)
    session.add_all(
        [
            ChainlinkTick(value=Decimal("100"), source_timestamp=start_time, received_at=start_time),
            ChainlinkTick(value=Decimal("101"), source_timestamp=now, received_at=now),
        ]
    )
    await _seed_orderbooks(session, market)


async def _seed_orderbooks(session: AsyncSession, market: Market) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            OrderbookSnapshot(
                market_id=market.id,
                token_id=market.up_token_id,
                outcome="UP",
                received_at=now,
                best_bid=Decimal("0.49"),
                best_ask=Decimal("0.90"),
                midpoint=Decimal("0.695"),
                spread=Decimal("0.01"),
                bids=[],
                asks=[],
            ),
            OrderbookSnapshot(
                market_id=market.id,
                token_id=market.down_token_id,
                outcome="DOWN",
                received_at=now,
                best_bid=Decimal("0.10"),
                best_ask=Decimal("0.11"),
                midpoint=Decimal("0.105"),
                spread=Decimal("0.01"),
                bids=[],
                asks=[],
            ),
        ]
    )


class TimeoutClobClient:
    async def get_orderbook(self, token_id: str):
        raise PolymarketHttpError(
            code="POLYMARKET_CLOB_TIMEOUT",
            message="timeout",
            endpoint="/book",
            technical_detail=f"timeout for {token_id}",
        )


async def _seed_order(
    session: AsyncSession,
    market: Market,
    *,
    outcome: str,
    price: Decimal,
    size: Decimal,
) -> None:
    session.add(
        Order(
            market_id=market.id,
            mode="paper",
            token_id=market.up_token_id if outcome == "UP" else market.down_token_id,
            outcome=outcome,
            side="BUY",
            order_type="FAK",
            price=price,
            size=size,
            size_matched=size,
            status="FILLED",
            raw_response={"simulated": True},
        )
    )


async def _seed_ticks(
    session: AsyncSession,
    market: Market,
    *,
    start_price: Decimal,
    end_price: Decimal,
) -> None:
    assert market.start_ts is not None
    assert market.end_ts is not None
    start_time = datetime.fromtimestamp(market.start_ts, tz=UTC)
    end_time = datetime.fromtimestamp(market.end_ts, tz=UTC)
    session.add_all(
        [
            ChainlinkTick(value=start_price, source_timestamp=start_time, received_at=start_time),
            ChainlinkTick(value=end_price, source_timestamp=end_time, received_at=end_time),
        ]
    )
