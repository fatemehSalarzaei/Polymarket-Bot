from collections.abc import AsyncIterator
from decimal import Decimal
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.bot import get_geoblock_client
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.audit import AuditLog
from app.models.order import Order
from app.models.settings import StrategySettings
from app.schemas.execution import GeoblockStatus, PlaceOrderRequest, PlaceOrderResult
from app.services.dashboard_broadcaster import DashboardBroadcaster
from app.services.execution_engine import ExecutionEngine
from app.services.geoblock import parse_geoblock_status
from app.services.polymarket_sdk import BackendOnlyClobSdkWrapper
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision
from app.services.user_ws import UserWebSocketListener
from app.tests.test_strategy_engine import _context, _market


class FakeSdkClient:
    def __init__(self, result: PlaceOrderResult) -> None:
        self.result = result
        self.requests: list[PlaceOrderRequest] = []

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        self.requests.append(request)
        return self.result


class FakeGeoblockClient:
    def __init__(self, status: GeoblockStatus) -> None:
        self.status = status

    async def get_status(self) -> GeoblockStatus:
        return self.status


class FakeUserWsConnection:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def __aiter__(self):
        self._iterator = iter(self.messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_dry_run_real_order_does_not_submit(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(PlaceOrderResult(submitted=True, status="SUBMITTED", external_order_id="order-1"))
    result = await _execute(sessionmaker, sdk_client=fake_sdk, dry_run=True, trading_enabled=True)

    assert result.status == "DRY_RUN"
    assert result.submitted is False
    assert fake_sdk.requests == []


@pytest.mark.asyncio
async def test_disabled_trading_blocks_real_order(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(PlaceOrderResult(submitted=True, status="SUBMITTED", external_order_id="order-1"))
    result = await _execute(sessionmaker, sdk_client=fake_sdk, dry_run=False, trading_enabled=False)

    assert result.status == "BLOCKED"
    assert "TRADING_DISABLED" in result.reasons
    assert fake_sdk.requests == []


@pytest.mark.asyncio
async def test_geoblock_blocks_real_order(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(PlaceOrderResult(submitted=True, status="SUBMITTED", external_order_id="order-1"))
    result = await _execute(
        sessionmaker,
        sdk_client=fake_sdk,
        dry_run=False,
        trading_enabled=True,
        geoblock_status=GeoblockStatus(blocked=True, raw_response={"blocked": True}),
    )

    assert result.status == "BLOCKED"
    assert "GEOBLOCK_BLOCKED" in result.reasons
    assert fake_sdk.requests == []


@pytest.mark.asyncio
async def test_real_trading_blocks_when_wallet_missing(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(PlaceOrderResult(submitted=True, status="SUBMITTED", external_order_id="order-1"))
    result = await _execute(
        sessionmaker,
        sdk_client=fake_sdk,
        dry_run=False,
        trading_enabled=True,
        wallet_configured=False,
        api_credentials_configured=False,
    )

    assert result.status == "BLOCKED"
    assert "WALLET_CONFIG_MISSING" in result.reasons
    assert fake_sdk.requests == []


@pytest.mark.asyncio
async def test_real_trading_blocks_when_api_credentials_missing(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(PlaceOrderResult(submitted=True, status="SUBMITTED", external_order_id="order-1"))
    result = await _execute(
        sessionmaker,
        sdk_client=fake_sdk,
        dry_run=False,
        trading_enabled=True,
        wallet_configured=True,
        api_credentials_configured=False,
    )

    assert result.status == "BLOCKED"
    assert "WALLET_API_CREDENTIALS_MISSING" in result.reasons
    assert fake_sdk.requests == []


@pytest.mark.asyncio
async def test_mocked_sdk_submit_success_persists_real_order(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(
        PlaceOrderResult(
            submitted=True,
            dry_run=False,
            status="SUBMITTED",
            external_order_id="order-1",
            raw_response={"id": "order-1"},
        )
    )
    result = await _execute(sessionmaker, sdk_client=fake_sdk, dry_run=False, trading_enabled=True)

    assert result.submitted is True
    assert result.external_order_id == "order-1"
    assert len(fake_sdk.requests) == 1

    async with sessionmaker() as session:
        order = (await session.execute(select(Order).where(Order.external_order_id == "order-1"))).scalar_one()
        assert order.mode == "real"
        assert order.status == "SUBMITTED"


@pytest.mark.asyncio
async def test_mocked_sdk_submit_failure_persists_error(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    fake_sdk = FakeSdkClient(
        PlaceOrderResult(
            submitted=False,
            dry_run=False,
            status="FAILED",
            raw_response={"error": "nope"},
            error_message="SDK_FAILED",
        )
    )
    result = await _execute(sessionmaker, sdk_client=fake_sdk, dry_run=False, trading_enabled=True)

    assert result.submitted is False
    assert result.status == "FAILED"
    assert result.reasons == ["SDK_FAILED"]

    async with sessionmaker() as session:
        order = (await session.execute(select(Order).where(Order.status == "FAILED"))).scalar_one()
        assert order.error_message == "SDK_FAILED"


def test_parse_geoblock_status_detects_blocked() -> None:
    assert parse_geoblock_status({"blocked": True}).blocked is True
    assert parse_geoblock_status({"blocked": False}).blocked is False


def test_geoblock_endpoint_uses_backend_client(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    app.dependency_overrides[get_geoblock_client] = lambda: FakeGeoblockClient(
        GeoblockStatus(blocked=True, raw_response={"blocked": True})
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/bot/geoblock-status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["blocked"] is True


def test_kill_switch_updates_settings_and_writes_audit_log(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        with TestClient(app) as client:
            response = client.post("/api/bot/kill-switch")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"kill_switch_active": True, "trading_enabled": False}

    import asyncio

    async def assert_db() -> None:
        async with sessionmaker() as session:
            settings = (await session.execute(select(StrategySettings))).scalar_one()
            audit = (await session.execute(select(AuditLog).where(AuditLog.action == "bot.kill_switch"))).scalar_one()
            assert settings.kill_switch_active is True
            assert settings.trading_enabled is False
            assert audit.after is not None
            assert audit.after["kill_switch_active"] is True

    asyncio.run(assert_db())


@pytest.mark.asyncio
async def test_user_websocket_listener_reconciles_order_update(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    result = await _execute(
        sessionmaker,
        sdk_client=FakeSdkClient(
            PlaceOrderResult(
                submitted=True,
                status="SUBMITTED",
                external_order_id="order-1",
                raw_response={"id": "order-1"},
            )
        ),
        dry_run=False,
        trading_enabled=True,
    )
    assert result.external_order_id == "order-1"

    broadcaster = DashboardBroadcaster()
    connection = FakeUserWsConnection(
        [json.dumps({"order_id": "order-1", "status": "FILLED", "size_matched": "12.5"})]
    )
    listener = UserWebSocketListener(
        url="wss://example.test/user",
        sessionmaker=sessionmaker,
        broadcaster=broadcaster,
        connect=lambda _: connection,
        sleep=_no_sleep,
    )

    await listener.run(max_messages=1)

    async with sessionmaker() as session:
        order = (await session.execute(select(Order).where(Order.external_order_id == "order-1"))).scalar_one()
        assert order.status == "FILLED"
        assert order.size_matched == Decimal("12.50000000")
        assert order.filled_at is not None
    assert broadcaster.latest_events["order_update"]["data"]["order_id"] == "order-1"


async def _execute(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    sdk_client: FakeSdkClient,
    dry_run: bool,
    trading_enabled: bool,
    geoblock_status: GeoblockStatus | None = None,
    wallet_configured: bool = True,
    api_credentials_configured: bool = True,
):
    async with sessionmaker() as session:
        market = _market()
        session.add(market)
        await session.commit()
        await session.refresh(market)

        context = _context(market_id=market.id, trading_enabled=trading_enabled)
        decision = await StrategyEngine().evaluate(context)
        persisted_decision = await persist_strategy_decision(session, market=market, decision=decision)
        sdk = BackendOnlyClobSdkWrapper(
            credentials_configured=wallet_configured and api_credentials_configured,
            sdk_client=sdk_client,
            wallet_configured=wallet_configured,
            api_credentials_configured=api_credentials_configured,
        )
        engine = ExecutionEngine(sdk=sdk, dry_run=dry_run)
        return await engine.submit_real_order(
            session,
            market=market,
            persisted_decision=persisted_decision,
            decision=decision,
            context=context,
            geoblock_status=geoblock_status or GeoblockStatus(blocked=False, raw_response={"blocked": False}),
        )


async def _no_sleep(_: float) -> None:
    return None
