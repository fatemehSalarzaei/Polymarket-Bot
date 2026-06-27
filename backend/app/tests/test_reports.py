from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.audit import AuditLog
from app.services.paper_trading import PaperTradingEngine
from app.services.settlement_worker import SettlementWorker
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


def test_pnl_summary_endpoint_returns_settled_paper_pnl(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    async def seed() -> None:
        async with sessionmaker() as session:
            market = _market()
            market.raw_event = {"btc_start_price": "100"}
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
            await SettlementWorker().settle_market(
                session,
                market=market,
                winning_outcome="UP",
                btc_end_price=Decimal("101"),
            )
            await session.commit()

    asyncio.run(seed())

    response = client.get("/api/pnl/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["paper_orders"] == 1
    assert body["real_orders"] == 0
    assert body["settled_markets"] == 1
    assert Decimal(body["paper_pnl"]) > 0
    assert body["winning_trades"] == 1


def test_logs_endpoint_returns_recent_audit_logs(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    async def seed() -> None:
        async with sessionmaker() as session:
            session.add(
                AuditLog(
                    actor="test",
                    action="report.test",
                    entity_type="unit",
                    entity_id="1",
                    before=None,
                    after={"ok": True},
                )
            )
            await session.commit()

    asyncio.run(seed())

    response = client.get("/api/logs")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["action"] == "report.test"
    assert body[0]["after"] == {"ok": True}

