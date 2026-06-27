from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.audit import AuditLog
from app.models.settings import StrategySettings


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


def test_get_strategy_settings_creates_safe_default_row(client: TestClient) -> None:
    response = client.get("/api/strategy/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["paper_trading_enabled"] is True
    assert body["trading_enabled"] is False
    assert body["kill_switch_active"] is False
    assert body["final_window_seconds"] == 180
    assert body["order_type"] == "FAK"


def test_patch_strategy_settings_updates_and_writes_audit_log(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    response = client.patch(
        "/api/strategy/settings",
        json={
            "final_window_seconds": 120,
            "min_edge": "0.06",
            "max_order_size_usd": "25",
            "order_type": "FOK",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["final_window_seconds"] == 120
    assert body["min_edge"] == "0.0600"
    assert body["max_order_size_usd"] == "25.00"
    assert body["order_type"] == "FOK"

    async def assert_db_state() -> None:
        async with sessionmaker() as session:
            settings = (await session.execute(select(StrategySettings))).scalar_one()
            assert settings.final_window_seconds == 120
            assert settings.trading_enabled is False

            audit = (await session.execute(select(AuditLog))).scalar_one()
            assert audit.action == "strategy_settings.patch"
            assert audit.entity_type == "strategy_settings"
            assert audit.before is not None
            assert audit.before["final_window_seconds"] == 180
            assert audit.after is not None
            assert audit.after["final_window_seconds"] == 120

    import asyncio

    asyncio.run(assert_db_state())


def test_patch_strategy_settings_rejects_invalid_values(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    response = client.patch("/api/strategy/settings", json={"max_spread": "-0.01"})

    assert response.status_code == 422

    async def assert_no_audit_logs() -> None:
        async with sessionmaker() as session:
            count = await session.scalar(select(func.count(AuditLog.id)))
            assert count == 0

    import asyncio

    asyncio.run(assert_no_audit_logs())

