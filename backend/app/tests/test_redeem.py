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
from app.models.user import User
from app.schemas.execution import GeoblockStatus
from app.services.polymarket_redeem_adapter import RedeemAdapterResult, SafeDryRunRedeemAdapter
from app.services.redeem_service import RedeemService
from app.services.auth import hash_password
from app.services.settlement_worker import SettlementWorker
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


@pytest.mark.asyncio
async def test_non_dry_run_missing_polygon_rpc_blocks_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        settings = _settings(redeem_dry_run=False, real_order_dry_run=False).model_copy(update={"polygon_rpc_url": ""})
        eligibility = await _service(settings=settings).check_redeem_eligibility(session, market, settlement)

    assert "POLYGON_RPC_URL_MISSING" in eligibility.reasons


@pytest.mark.asyncio
async def test_redeem_amount_is_computed_from_balance_delta(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        result = await RedeemService(
            settings=_settings(redeem_dry_run=False, real_order_dry_run=False),
            adapter=BalanceDeltaRedeemAdapter(wallet_address="0x0000000000000000000000000000000000000001"),
            geoblock_client=FakeGeoblockClient(blocked=False),
        ).redeem_winning_position(session, market, settlement)
        await session.commit()

    assert result.status == "REDEEM_CONFIRMED"
    assert result.amount_redeemed == Decimal("2.5")
    assert result.record is not None
    assert result.record.raw_response["collateral_token_address"] == "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"


@pytest.mark.asyncio
async def test_missing_balance_after_keeps_amount_none_with_reason(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        result = await RedeemService(
            settings=_settings(redeem_dry_run=False, real_order_dry_run=False),
            adapter=MissingBalanceAfterRedeemAdapter(wallet_address="0x0000000000000000000000000000000000000001"),
            geoblock_client=FakeGeoblockClient(blocked=False),
        ).redeem_winning_position(session, market, settlement)
        await session.commit()

    assert result.status == "REDEEM_CONFIRMED"
    assert result.amount_redeemed is None
    assert result.record is not None
    assert result.record.raw_response["amount_redeemed_unavailable_reason"] == "BALANCE_AFTER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_reverted_redeem_transaction_does_not_store_amount(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        result = await RedeemService(
            settings=_settings(redeem_dry_run=False, real_order_dry_run=False),
            adapter=RevertedRedeemAdapter(wallet_address="0x0000000000000000000000000000000000000001"),
            geoblock_client=FakeGeoblockClient(blocked=False),
        ).redeem_winning_position(session, market, settlement)
        await session.commit()

    assert result.status == "REDEEM_FAILED"
    assert result.amount_redeemed is None
    assert result.error_message == "REDEEM_TX_REVERTED"


@pytest.mark.asyncio
async def test_non_dry_run_missing_collateral_token_blocks_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market, settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"))
        await session.commit()

        settings = _settings(redeem_dry_run=False, real_order_dry_run=False).model_copy(
            update={"collateral_token_address": "", "pusd_contract_address": ""}
        )
        eligibility = await _service(settings=settings).check_redeem_eligibility(session, market, settlement)

    assert "COLLATERAL_TOKEN_MISSING" in eligibility.reasons


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


@pytest.mark.asyncio
async def test_redeem_task_is_user_scoped_for_shared_market(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        user_one = User(username="winner", email="winner@example.com", password_hash=hash_password("password1234"))
        user_two = User(username="loser", email="loser@example.com", password_hash=hash_password("password1234"))
        session.add_all([user_one, user_two])
        await session.flush()
        market, _settlement = await _seed_settlement(session)
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"), user_id=user_one.id)
        await _seed_order(session, market, mode="real", outcome="DOWN", size_matched=Decimal("5"), user_id=user_two.id)
        await session.commit()

    result = await redeem_resolved_winning_positions_job(sessionmaker=sessionmaker, service=_service())

    async with sessionmaker() as session:
        records = list((await session.execute(select(RedeemRecord))).scalars().all())

    assert result["processed"] == 1
    assert len(records) == 1
    assert records[0].user_id == user_one.id


@pytest.mark.asyncio
async def test_internal_settlement_redeem_record_waits_for_official_resolution(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        market = Market(
            event_slug="btc-updown-internal",
            market_slug="btc-updown-internal",
            condition_id="condition-internal",
            question="BTC Up or Down",
            active=False,
            closed=True,
            up_token_id="up-token",
            down_token_id="down-token",
            raw_event={},
            raw_market={},
        )
        session.add(market)
        await session.flush()
        await _seed_order(session, market, mode="real", outcome="UP", size_matched=Decimal("5"), user_id=7)

        await SettlementWorker().settle_market(session, market=market, winning_outcome="UP", user_id=7)
        records = list((await session.execute(select(RedeemRecord))).scalars().all())

    assert len(records) == 1
    assert records[0].status == "NOT_ELIGIBLE"
    assert records[0].error_message == "OFFICIAL_RESOLUTION_MISSING"


class FakeGeoblockClient:
    def __init__(self, *, blocked: bool = False) -> None:
        self.blocked = blocked

    async def get_status(self) -> GeoblockStatus:
        return GeoblockStatus(blocked=self.blocked, raw_response={"blocked": self.blocked})


class NotImplementedRedeemAdapter(SafeDryRunRedeemAdapter):
    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        raise NotImplementedError("Real provider must implement redeemPositions")


class BalanceDeltaRedeemAdapter(SafeDryRunRedeemAdapter):
    wallet_address = "0x0000000000000000000000000000000000000001"
    wallet_credential_id = 12

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return RedeemAdapterResult(
            submitted=True,
            confirmed=True,
            tx_hash="0xtx",
            raw_response={"condition_id": condition_id, "index_sets": index_sets},
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        if not hasattr(self, "_called"):
            self._called = True
            return Decimal("10")
        return Decimal("12.5")


class MissingBalanceAfterRedeemAdapter(SafeDryRunRedeemAdapter):
    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return RedeemAdapterResult(
            submitted=True,
            confirmed=True,
            tx_hash="0xtx",
            raw_response={"condition_id": condition_id, "index_sets": index_sets},
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        if not hasattr(self, "_called"):
            self._called = True
            return Decimal("10")
        return None


class RevertedRedeemAdapter(SafeDryRunRedeemAdapter):
    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return RedeemAdapterResult(
            submitted=True,
            confirmed=False,
            tx_hash="0xtx",
            raw_response={"condition_id": condition_id, "index_sets": index_sets},
            error_message="REDEEM_TX_REVERTED",
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        return Decimal("10")


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
        polygon_rpc_url="https://polygon-rpc.example",
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
    if not config.private_key:
        return RedeemService(settings=config, geoblock_client=FakeGeoblockClient(blocked=geoblocked))
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
    user_id: int | None = None,
) -> Order:
    order = Order(
        user_id=user_id,
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
