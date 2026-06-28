from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.redeem import get_redeem_service
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settings import StrategySettings
from app.models.settlement import Settlement
from app.schemas.execution import GeoblockStatus
from app.services.polymarket_redeem_adapter import RedeemAdapterResult, SafeDryRunRedeemAdapter
from app.services.redeem_service import RedeemService
from app.tasks.redeem_tasks import redeem_resolved_winning_positions_job, redeem_resolved_winning_positions_task


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
    app.dependency_overrides[get_redeem_service] = lambda: _service()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_paper_only_winning_settlement_does_not_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="paper", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        eligibility = await _service().check_redeem_eligibility(session, market, settlement)

    assert eligibility.status == "SKIPPED_PAPER_ONLY"
    assert "PAPER_ONLY" in eligibility.reasons


@pytest.mark.asyncio
async def test_losing_real_order_does_not_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="DOWN", size_matched=Decimal("5"))
        await session.commit()

        eligibility = await _service().check_redeem_eligibility(session, market, settlement)

    assert eligibility.status == "NOT_ELIGIBLE"
    assert "WINNING_REAL_ORDER_MISSING" in eligibility.reasons


@pytest.mark.asyncio
async def test_winning_real_order_creates_skipped_dry_run(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        result = await _service().redeem_winning_position(session, market, settlement)
        await session.commit()

    assert result.status == "SKIPPED_DRY_RUN"
    assert result.tx_hash is None
    assert result.amount_redeemed is None


@pytest.mark.asyncio
async def test_duplicate_redeem_record_is_prevented(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        await _service().redeem_winning_position(session, market, settlement)
        await _service().redeem_winning_position(session, market, settlement)
        await session.commit()

        records = list((await session.execute(select(RedeemRecord))).scalars().all())

    assert len(records) == 1
    assert records[0].status == "SKIPPED_DRY_RUN"


@pytest.mark.asyncio
async def test_kill_switch_blocks_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session, kill_switch=True)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        eligibility = await _service().check_redeem_eligibility(session, market, settlement)

    assert "KILL_SWITCH_ACTIVE" in eligibility.reasons


@pytest.mark.asyncio
async def test_credentials_missing_blocks_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        eligibility = await _service(settings=_settings(with_credentials=False)).check_redeem_eligibility(
            session,
            market,
            settlement,
        )

    assert "CREDENTIALS_MISSING" in eligibility.reasons


@pytest.mark.asyncio
async def test_geoblock_blocked_blocks_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        eligibility = await _service(geoblocked=True).check_redeem_eligibility(session, market, settlement)

    assert "GEOBLOCK_BLOCKED" in eligibility.reasons


@pytest.mark.asyncio
async def test_existing_confirmed_prevents_another_attempt(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        session.add(
            RedeemRecord(
                market_id=market.id,
                settlement_id=settlement.id,
                condition_id=market.condition_id,
                winning_outcome="UP",
                status="REDEEM_CONFIRMED",
                mode="real",
                tx_hash="0xabc",
                raw_request={},
                raw_response={"confirmed": True},
            )
        )
        await session.commit()

        result = await _service().redeem_winning_position(session, market, settlement)
        await session.commit()

        records = list((await session.execute(select(RedeemRecord))).scalars().all())

    assert len(records) == 1
    assert result.status == "REDEEM_CONFIRMED"
    assert records[0].tx_hash == "0xabc"


@pytest.mark.asyncio
async def test_non_dry_run_not_implemented_is_stored_as_failed(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        result = await _service(settings=_settings(redeem_dry_run=False, real_order_dry_run=False)).redeem_winning_position(
            session,
            market,
            settlement,
        )
        await session.commit()

    assert result.status == "REDEEM_FAILED"
    assert "redeemPositions" in (result.error_message or "")


def test_redeem_api_endpoints_return_statuses(
    client: TestClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    async def seed() -> int:
        async with sessionmaker() as session:
            market, _settlement = await _seed_settlement(session)
            await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
            await session.commit()
            return market.id

    market_id = asyncio.run(seed())

    status = client.get(f"/api/redeems/{market_id}")
    attempt = client.post(f"/api/redeems/{market_id}/attempt")
    records = client.get("/api/redeems")

    assert status.status_code == 200
    assert status.json()["status"] == "SKIPPED_DRY_RUN"
    assert attempt.status_code == 200
    assert attempt.json()["status"] == "SKIPPED_DRY_RUN"
    assert records.status_code == 200
    assert records.json()[0]["status"] == "SKIPPED_DRY_RUN"


@pytest.mark.asyncio
async def test_celery_redeem_task_imports_and_runs_safely(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    assert redeem_resolved_winning_positions_task.name == "app.tasks.redeem.redeem_resolved_winning_positions"

    async with sessionmaker() as session:
        market, _settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

    result = await redeem_resolved_winning_positions_job(sessionmaker=sessionmaker, service=_service())

    assert result["processed"] == 1
    assert result["redeems"][0]["status"] == "SKIPPED_DRY_RUN"


class FakeGeoblockClient:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked

    async def get_status(self) -> GeoblockStatus:
        return GeoblockStatus(blocked=self.blocked, raw_response={"blocked": self.blocked})


class NotImplementedRedeemAdapter(SafeDryRunRedeemAdapter):
    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        raise NotImplementedError("Real provider must implement redeemPositions")


def _settings(
    *,
    with_credentials: bool = True,
    redeem_dry_run: bool = True,
    real_order_dry_run: bool = True,
) -> Settings:
    credentials = {
        "private_key": "private",
        "polymarket_api_key": "key",
        "polymarket_api_secret": "secret",
        "polymarket_api_passphrase": "passphrase",
        "polymarket_funder_address": "0xwallet",
    }
    if not with_credentials:
        credentials = {}
    return Settings(
        database_url="sqlite+aiosqlite:///unused.db",
        redis_url="redis://localhost:6379/0",
        redeem_enabled=True,
        redeem_dry_run=redeem_dry_run,
        real_order_dry_run=real_order_dry_run,
        **credentials,
    )


def _service(
    *,
    settings: Settings | None = None,
    geoblocked: bool = False,
) -> RedeemService:
    config = settings or _settings()
    adapter = (
        NotImplementedRedeemAdapter(wallet_address=config.polymarket_funder_address or None)
        if not config.redeem_dry_run and not config.real_order_dry_run
        else SafeDryRunRedeemAdapter(wallet_address=config.polymarket_funder_address or None)
    )
    return RedeemService(settings=config, adapter=adapter, geoblock_client=FakeGeoblockClient(blocked=geoblocked))


async def _seed_settlement(
    session: AsyncSession,
    *,
    winning_outcome: str = "UP",
    kill_switch: bool = False,
) -> tuple[Market, Settlement]:
    settings = StrategySettings(trading_enabled=True, kill_switch_active=kill_switch)
    market = Market(
        event_slug=f"btc-updown-15m-test-{id(session)}-{winning_outcome}-{kill_switch}",
        market_slug="btc-updown-15m-test",
        condition_id=f"condition-{id(session)}-{winning_outcome}-{kill_switch}",
        question="BTC Up or Down",
        active=False,
        closed=True,
        start_ts=1,
        end_ts=2,
        up_token_id="up-token",
        down_token_id="down-token",
        raw_event={},
        raw_market={},
    )
    session.add_all([settings, market])
    await session.flush()
    settlement = Settlement(
        market_id=market.id,
        winning_outcome=winning_outcome,
        resolved_at=datetime.now(UTC),
        paper_pnl=Decimal("0"),
        real_pnl=Decimal("0"),
        raw_resolution={"official": True},
    )
    session.add(settlement)
    await session.flush()
    await session.refresh(market)
    await session.refresh(settlement)
    return market, settlement


async def _seed_order(
    session: AsyncSession,
    market: Market,
    *,
    mode: str,
    outcome: str,
    size_matched: Decimal,
) -> Order:
    order = Order(
        market_id=market.id,
        mode=mode,
        token_id=market.up_token_id if outcome == "UP" else market.down_token_id,
        outcome=outcome,
        side="BUY",
        order_type="FAK",
        price=Decimal("0.50"),
        size=size_matched,
        size_matched=size_matched,
        status="FILLED",
        raw_response={"test": True},
    )
    session.add(order)
    await session.flush()
    await session.refresh(order)
    return order
