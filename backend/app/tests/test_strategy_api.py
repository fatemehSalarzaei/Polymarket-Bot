from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.services.paper_trading import PaperTradingEngine
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision
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


def test_decision_history_and_orders_endpoints_return_persisted_rows(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    async def seed() -> None:
        async with sessionmaker() as session:
            market = _market()
            session.add(market)
            await session.commit()
            await session.refresh(market)

            context = _context(market_id=market.id)
            decision = await StrategyEngine().evaluate(context)
            persisted = await persist_strategy_decision(session, market=market, decision=decision)
            await PaperTradingEngine().create_order(
                session,
                market=market,
                persisted_decision=persisted,
                decision=decision,
                context=context,
            )
            await session.commit()

    asyncio.run(seed())

    current = client.get("/api/strategy/current-decision")
    history = client.get("/api/strategy/decisions")
    orders = client.get("/api/orders")

    assert current.status_code == 200
    assert current.json()["decision"] == "BUY_UP"
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert orders.status_code == 200
    assert orders.json()[0]["mode"] == "paper"
    assert orders.json()[0]["price"] == "0.90000000"


def test_current_decision_endpoint_returns_404_when_empty(client: TestClient) -> None:
    response = client.get("/api/strategy/current-decision")

    assert response.status_code == 404
