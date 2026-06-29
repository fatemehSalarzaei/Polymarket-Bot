from __future__ import annotations

from collections.abc import AsyncIterator
import asyncio

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.bot import get_geoblock_client
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.schemas.execution import GeoblockStatus
from app.schemas.wallet import WalletConfigureRequest
from app.services.wallet_credentials import configure_wallet

PRIVATE_KEY = "0x0000000000000000000000000000000000000000000000000000000000000001"


class FakeCredentialDeriver:
    async def create_or_derive_api_credentials(self, **kwargs):
        return {
            "api_key": "api-key",
            "api_secret": "api-secret",
            "api_passphrase": "api-passphrase",
        }


class FakeGeoblockClient:
    def __init__(self, *, blocked: bool, checked: bool = True) -> None:
        self.blocked = blocked
        self.checked = checked

    async def get_status(self) -> GeoblockStatus:
        return GeoblockStatus(blocked=self.blocked, checked=self.checked, raw_response={})


@pytest.fixture(autouse=True)
def settings_env(monkeypatch) -> AsyncIterator[None]:
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("REAL_ORDER_DRY_RUN", "true")
    monkeypatch.setenv("TRADING_ENABLED", "false")
    monkeypatch.setenv("REAL_TRADING_CONFIRMATION_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    app.dependency_overrides[get_geoblock_client] = lambda: FakeGeoblockClient(blocked=True)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_dry_run_mode_treats_geoblock_as_warning(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    _seed_ready_wallet(sessionmaker)

    response = client.get("/api/trading/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_dry_run"] is True
    assert body["trading_ready"] is True
    assert body["dry_run_trading_ready"] is True
    assert body["real_trading_ready"] is False
    assert body["real_trading_available"] is False
    assert "GEOBLOCK_BLOCKED" in body["warnings"]
    assert "GEOBLOCK_BLOCKED" not in body["blocking_reasons"]
    assert "GEOBLOCK_BLOCKED" in body["real_trading_blocking_reasons"]

    enable_response = client.post("/api/trading/enable", json={"confirm_phrase": "ENABLE REAL TRADING"})

    assert enable_response.status_code == 200
    assert enable_response.json()["mode"] == "dry_run"
    assert enable_response.json()["trading_enabled"] is True


def test_real_mode_keeps_geoblock_as_hard_blocker(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    monkeypatch.setenv("REAL_ORDER_DRY_RUN", "false")
    monkeypatch.setenv("TRADING_ENABLED", "true")
    monkeypatch.setenv("REAL_TRADING_CONFIRMATION_ENABLED", "true")
    get_settings.cache_clear()
    _seed_ready_wallet(sessionmaker)

    response = client.get("/api/trading/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["real_order_dry_run"] is False
    assert body["trading_ready"] is False
    assert body["real_trading_ready"] is False
    assert body["real_trading_available"] is False
    assert "GEOBLOCK_BLOCKED" in body["blocking_reasons"]
    assert "GEOBLOCK_BLOCKED" in body["real_trading_blocking_reasons"]

    enable_response = client.post("/api/trading/enable", json={"confirm_phrase": "ENABLE REAL TRADING"})

    assert enable_response.status_code == 409


def test_real_mode_can_enable_when_all_real_safety_checks_pass(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch,
) -> None:
    monkeypatch.setenv("REAL_ORDER_DRY_RUN", "false")
    monkeypatch.setenv("TRADING_ENABLED", "true")
    monkeypatch.setenv("REAL_TRADING_CONFIRMATION_ENABLED", "true")
    get_settings.cache_clear()
    app.dependency_overrides[get_geoblock_client] = lambda: FakeGeoblockClient(blocked=False)
    _seed_ready_wallet(sessionmaker)

    response = client.get("/api/trading/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["trading_ready"] is True
    assert body["real_trading_ready"] is True
    assert body["real_trading_available"] is True
    assert body["blocking_reasons"] == []

    enable_response = client.post("/api/trading/enable", json={"confirm_phrase": "ENABLE REAL TRADING"})

    assert enable_response.status_code == 200
    assert enable_response.json()["mode"] == "real"
    assert enable_response.json()["trading_enabled"] is True


def _seed_ready_wallet(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async def seed() -> None:
        async with sessionmaker() as session:
            await configure_wallet(
                WalletConfigureRequest(private_key=PRIVATE_KEY),
                session,
                deriver=FakeCredentialDeriver(),
            )

    asyncio.run(seed())
