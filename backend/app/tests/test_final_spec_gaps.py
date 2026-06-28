from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.tick import ChainlinkTick
from app.schemas.execution import GeoblockStatus, PlaceOrderResult
from app.services.execution_engine import ExecutionEngine
from app.services.polymarket_clob import normalize_orderbook
from app.services.polymarket_sdk import BackendOnlyClobSdkWrapper
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision
from app.tests.test_execution_engine import FakeSdkClient
from app.tests.test_strategy_engine import _context, _market


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


def test_bot_status_start_stop_endpoints(client: TestClient) -> None:
    assert client.get("/api/bot/status").json()["running"] is False
    assert client.post("/api/bot/start").json()["running"] is True
    assert client.post("/api/bot/stop").json()["running"] is False


def test_current_btc_endpoint_returns_latest_tick(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    async def seed() -> None:
        async with sessionmaker() as session:
            session.add(ChainlinkTick(value=Decimal("61000"), raw_payload={"symbol": "btc/usd"}))
            await session.commit()

    asyncio.run(seed())
    response = client.get("/api/markets/current/btc")

    assert response.status_code == 200
    assert response.json()["value"] == "61000.00000000"


@pytest.mark.asyncio
async def test_strategy_buy_down_when_down_ask_is_higher() -> None:
    decision = await StrategyEngine().evaluate(
        _context(
            up_ask=Decimal("0.12"),
            down_ask=Decimal("0.82"),
            down_spread=Decimal("0.01"),
        )
    )

    assert decision.decision == "BUY_DOWN"
    assert decision.outcome == "DOWN"


def test_empty_orderbook_normalization_handles_no_levels() -> None:
    dto = normalize_orderbook({"asset_id": "token", "bids": [], "asks": []})

    assert dto.best_bid is None
    assert dto.best_ask is None
    assert dto.midpoint is None
    assert dto.spread is None


@pytest.mark.asyncio
async def test_daily_loss_blocks_real_order(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(PlaceOrderResult(submitted=True, status="SUBMITTED", external_order_id="order-1"))
    async with sessionmaker() as session:
        market = _market()
        session.add(market)
        await session.commit()
        await session.refresh(market)

        context = _context(market_id=market.id, trading_enabled=True)
        decision = await StrategyEngine().evaluate(context)
        persisted_decision = await persist_strategy_decision(session, market=market, decision=decision)
        engine = ExecutionEngine(
            sdk=BackendOnlyClobSdkWrapper(credentials_configured=True, sdk_client=fake_sdk),
            dry_run=False,
        )
        result = await engine.submit_real_order(
            session,
            market=market,
            persisted_decision=persisted_decision,
            decision=decision,
            context=context,
            geoblock_status=GeoblockStatus(blocked=False, raw_response={"blocked": False}),
            daily_loss_usd=Decimal("50"),
        )

    assert result.status == "BLOCKED"
    assert "DAILY_LOSS_LIMIT_REACHED" in result.reasons
    assert fake_sdk.requests == []
