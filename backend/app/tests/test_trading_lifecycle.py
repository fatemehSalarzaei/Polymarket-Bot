from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settlement import Settlement
from app.models.settings import StrategySettings
from app.models.tick import ChainlinkTick
from app.schemas.execution import GeoblockStatus, PlaceOrderResult
from app.services.execution_engine import ExecutionEngine
from app.services.order_reconciler import OrderReconciler
from app.services.polymarket_resolution import OfficialResolution
from app.services.polymarket_redeem_adapter import RedeemAdapterResult
from app.services.polymarket_sdk import BackendOnlyClobSdkWrapper
from app.services.redeem_service import RedeemService
from app.services.runtime_gate import set_bot_running
from app.services.settlement_worker import SettlementWorker
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision
from app.tasks.strategy_tasks import evaluate_current_strategy_job


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
async def test_paper_only_full_cycle_does_not_create_redeem(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market = _market("paper-cycle")
        session.add(market)
        await session.flush()
        decision = await StrategyEngine().evaluate(_context(market, paper_trading_enabled=True, trading_enabled=False))
        persisted = await persist_strategy_decision(session, market=market, decision=decision)
        session.add(
            Order(
                market_id=market.id,
                strategy_decision_id=persisted.id,
                mode="paper",
                token_id=market.up_token_id,
                outcome="UP",
                side="BUY",
                order_type="FAK",
                price=Decimal("0.50"),
                size=Decimal("2"),
                size_matched=Decimal("2"),
                status="FILLED",
                raw_response={"simulated": True},
            )
        )
        await _seed_ticks(session, market, start_price=Decimal("100"), end_price=Decimal("101"))
        settlement = await SettlementWorker(resolution_client=FakeResolutionClient(None)).settle_market(
            session,
            market=market,
            winning_outcome="UP",
            btc_start_price=Decimal("100"),
            btc_end_price=Decimal("101"),
        )
        await session.commit()

        records = list((await session.execute(select(RedeemRecord))).scalars().all())

    assert settlement.paper_pnl == Decimal("1.00000000")
    assert settlement.real_pnl == Decimal("0E-8")
    assert records == []


@pytest.mark.asyncio
async def test_real_dry_run_cycle_records_no_matched_size(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market = _market("dry-run")
        session.add(market)
        await session.flush()
        decision = await StrategyEngine().evaluate(_context(market, paper_trading_enabled=False, trading_enabled=True))
        persisted = await persist_strategy_decision(session, market=market, decision=decision)

        result = await ExecutionEngine(sdk=_sdk(), dry_run=True).submit_real_order(
            session,
            market=market,
            persisted_decision=persisted,
            decision=decision,
            context=_context(market, paper_trading_enabled=False, trading_enabled=True),
            geoblock_status=GeoblockStatus(blocked=False),
        )

    assert result.status == "DRY_RUN"
    assert result.dry_run is True
    assert result.submitted is False


@pytest.mark.asyncio
async def test_successful_real_order_reconciles_settles_officially_and_redeems(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        market = _market("real-cycle", condition_id="0x" + "11" * 32)
        session.add_all([market, StrategySettings(trading_enabled=True)])
        await session.flush()
        context = _context(market, paper_trading_enabled=False, trading_enabled=True)
        decision = await StrategyEngine().evaluate(context)
        persisted = await persist_strategy_decision(session, market=market, decision=decision)
        real_enabled_settings = get_settings().model_copy(
            update={
                "trading_enabled": True,
                "real_trading_confirmation_enabled": True,
                "real_order_dry_run": False,
            }
        )
        submit_result = await ExecutionEngine(
            sdk=_sdk(FakeOrderSdk()),
            dry_run=False,
            settings=real_enabled_settings,
        ).submit_real_order(
            session,
            market=market,
            persisted_decision=persisted,
            decision=decision,
            context=context,
            geoblock_status=GeoblockStatus(blocked=False),
        )
        assert submit_result.status == "SUBMITTED"

        order = (await session.execute(select(Order).where(Order.id == submit_result.order_id))).scalar_one()
        await OrderReconciler().apply_user_update_for_order(
            session,
            order=order,
            payload={"order_id": "real-order-1", "status": "filled", "size_matched": "1"},
        )
        settlement = await SettlementWorker(resolution_client=FakeResolutionClient("UP")).settle_market(
            session,
            market=market,
            winning_outcome="UP",
            official_resolution=OfficialResolution(True, "UP", raw_response={"mock": True}),
        )
        redeem_result = await RedeemService(
            settings=get_settings().model_copy(update={"redeem_enabled": True, "redeem_dry_run": False, "real_order_dry_run": False}),
            adapter=FakeRedeemAdapter(),
            geoblock_client=FakeGeoblock(blocked=False),
        ).redeem_winning_position(session, market, settlement)
        await session.commit()

        refreshed_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()

    assert refreshed_order.status == "SETTLEMENT_ELIGIBLE"
    assert settlement.raw_resolution["official"] is True
    assert redeem_result.status == "REDEEM_CONFIRMED"
    assert redeem_result.tx_hash == "0xtx"
    assert redeem_result.balance_before == Decimal("10")
    assert redeem_result.balance_after == Decimal("11")


@pytest.mark.asyncio
async def test_geoblock_blocks_real_order(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market = _market("geoblock")
        session.add(market)
        await session.flush()
        context = _context(market, trading_enabled=True)
        decision = await StrategyEngine().evaluate(context)
        persisted = await persist_strategy_decision(session, market=market, decision=decision)

        result = await ExecutionEngine(sdk=_sdk(FakeOrderSdk()), dry_run=False).submit_real_order(
            session,
            market=market,
            persisted_decision=persisted,
            decision=decision,
            context=context,
            geoblock_status=GeoblockStatus(blocked=True),
        )

    assert result.status == "BLOCKED"
    assert "GEOBLOCK_BLOCKED" in result.reasons


@pytest.mark.asyncio
async def test_real_order_non_dry_run_requires_env_confirmation(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market = _market("env-block")
        session.add(market)
        await session.flush()
        context = _context(market, trading_enabled=True)
        decision = await StrategyEngine().evaluate(context)
        persisted = await persist_strategy_decision(session, market=market, decision=decision)
        sdk = FakeOrderSdk()

        result = await ExecutionEngine(sdk=_sdk(sdk), dry_run=False).submit_real_order(
            session,
            market=market,
            persisted_decision=persisted,
            decision=decision,
            context=context,
            geoblock_status=GeoblockStatus(blocked=False),
        )

    assert result.status == "BLOCKED"
    assert "REAL_TRADING_ENV_DISABLED" in result.reasons
    assert "REAL_TRADING_CONFIRMATION_DISABLED" in result.reasons
    assert sdk.requests == []


@pytest.mark.asyncio
async def test_bot_stop_prevents_strategy_execution(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await set_bot_running(session, False)
        await session.commit()

    result = await evaluate_current_strategy_job(sessionmaker=sessionmaker)

    assert result == {"skipped": True, "reason": "BOT_STOPPED"}


@pytest.mark.asyncio
async def test_real_trading_decision_works_when_paper_trading_disabled() -> None:
    decision = await StrategyEngine().evaluate(
        _context(_market("paper-disabled"), paper_trading_enabled=False, trading_enabled=True)
    )

    assert decision.decision == "BUY_UP"
    assert "PAPER_TRADING_DISABLED" not in decision.risk_reasons


class FakeOrderSdk:
    def __init__(self) -> None:
        self.requests = []

    async def place_order(self, request):
        self.requests.append(request)
        return PlaceOrderResult(
            submitted=True,
            status="SUBMITTED",
            external_order_id="real-order-1",
            raw_response={"orderID": "real-order-1"},
        )

    async def get_order(self, order_id: str) -> dict:
        return {"order_id": order_id, "status": "filled", "size_matched": "1"}


class FakeResolutionClient:
    def __init__(self, winning_outcome: str | None) -> None:
        self._winning_outcome = winning_outcome

    async def get_official_resolution(self, market: Market) -> OfficialResolution:
        if self._winning_outcome is None:
            return OfficialResolution(False, reason="mock_internal_only")
        return OfficialResolution(True, self._winning_outcome, raw_response={"mock": True})


class FakeGeoblock:
    def __init__(self, *, blocked: bool) -> None:
        self._blocked = blocked

    async def get_status(self) -> GeoblockStatus:
        return GeoblockStatus(blocked=self._blocked)


class FakeRedeemAdapter:
    credentials_configured = True
    wallet_address = "0x0000000000000000000000000000000000000001"
    wallet_credential_id = 42

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return RedeemAdapterResult(
            submitted=True,
            confirmed=True,
            tx_hash="0xtx",
            amount_redeemed=Decimal("1"),
            raw_response={"condition_id": condition_id, "index_sets": index_sets},
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        if not hasattr(self, "_called"):
            self._called = True
            return Decimal("10")
        return Decimal("11")


def _sdk(sdk_client=None) -> BackendOnlyClobSdkWrapper:
    return BackendOnlyClobSdkWrapper(credentials_configured=True, sdk_client=sdk_client or FakeOrderSdk())


def _market(slug: str, *, condition_id: str | None = None) -> Market:
    now_ts = int(datetime.now(UTC).timestamp())
    return Market(
        event_slug=f"btc-updown-15m-{slug}",
        market_slug=f"btc-updown-15m-{slug}-market",
        condition_id=condition_id or f"condition-{slug}",
        question="BTC Up or Down",
        active=True,
        closed=False,
        start_ts=now_ts - 800,
        end_ts=now_ts + 100,
        up_token_id=f"up-token-{slug}",
        down_token_id=f"down-token-{slug}",
        raw_event={},
        raw_market={},
    )


def _context(market: Market, **overrides):
    values = {
        "market_id": market.id or 1,
        "event_slug": market.event_slug,
        "up_token_id": market.up_token_id,
        "down_token_id": market.down_token_id,
        "time_remaining_seconds": 100,
        "up_bid": Decimal("0.49"),
        "up_ask": Decimal("0.90"),
        "up_spread": Decimal("0.01"),
        "down_bid": Decimal("0.10"),
        "down_ask": Decimal("0.11"),
        "down_spread": Decimal("0.01"),
        "market_data_age_seconds": Decimal("1"),
        "paper_trading_enabled": True,
        "trading_enabled": False,
        "kill_switch_active": False,
        "final_window_seconds": 180,
        "min_edge": Decimal("0.05"),
        "max_spread": Decimal("0.03"),
        "max_slippage": Decimal("0.02"),
        "max_order_size_usd": Decimal("1"),
        "max_daily_loss_usd": Decimal("1"),
        "max_data_age_seconds": 10,
        "order_type": "FAK",
    }
    values.update(overrides)
    from app.schemas.strategy import StrategyContext

    return StrategyContext(**values)


async def _seed_ticks(session: AsyncSession, market: Market, *, start_price: Decimal, end_price: Decimal) -> None:
    assert market.start_ts is not None
    assert market.end_ts is not None
    session.add_all(
        [
            ChainlinkTick(
                value=start_price,
                source_timestamp=datetime.fromtimestamp(market.start_ts, tz=UTC),
                received_at=datetime.fromtimestamp(market.start_ts, tz=UTC),
            ),
            ChainlinkTick(
                value=end_price,
                source_timestamp=datetime.fromtimestamp(market.end_ts, tz=UTC),
                received_at=datetime.fromtimestamp(market.end_ts, tz=UTC),
            ),
        ]
    )
