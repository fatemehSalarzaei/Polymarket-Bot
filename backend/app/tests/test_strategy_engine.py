from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.market import Market
from app.models.order import Order
from app.models.strategy import StrategyDecision
from app.schemas.strategy import StrategyContext
from app.services.paper_trading import PaperTradingEngine
from app.services.risk_manager import RiskManager
from app.services.strategy_engine import StrategyEngine
from app.services.strategy_persistence import persist_strategy_decision


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
async def test_strategy_returns_no_trade_before_final_window() -> None:
    decision = await StrategyEngine().evaluate(_context(time_remaining_seconds=240))

    assert decision.decision == "NO_TRADE"
    assert decision.reason == "NOT_IN_FINAL_WINDOW"
    assert "NOT_IN_FINAL_WINDOW" in decision.risk_reasons


@pytest.mark.asyncio
async def test_strategy_returns_buy_up_when_up_ask_higher_by_min_gap() -> None:
    decision = await StrategyEngine().evaluate(
        _context(
            up_ask=Decimal("0.90"),
            down_ask=Decimal("0.11"),
            min_edge=Decimal("0.05"),
        )
    )

    assert decision.decision == "BUY_UP"
    assert decision.outcome == "UP"
    assert decision.market_price == Decimal("0.90")
    assert decision.compared_up_value == Decimal("0.90")
    assert decision.compared_down_value == Decimal("0.11")
    assert decision.price_gap == Decimal("0.79")
    assert decision.edge == Decimal("0.79")
    assert decision.reason == "HIGHER_UP_MARKET_PRICE"


@pytest.mark.asyncio
async def test_strategy_returns_buy_down_when_down_ask_higher_by_min_gap() -> None:
    decision = await StrategyEngine().evaluate(
        _context(
            up_ask=Decimal("0.14"),
            down_ask=Decimal("0.83"),
            min_edge=Decimal("0.05"),
        )
    )

    assert decision.decision == "BUY_DOWN"
    assert decision.outcome == "DOWN"
    assert decision.market_price == Decimal("0.83")
    assert decision.price_gap == Decimal("0.69")
    assert decision.edge == Decimal("0.69")
    assert decision.reason == "HIGHER_DOWN_MARKET_PRICE"


@pytest.mark.asyncio
async def test_strategy_returns_price_gap_too_small() -> None:
    decision = await StrategyEngine().evaluate(
        _context(
            up_ask=Decimal("0.51"),
            down_ask=Decimal("0.50"),
            min_edge=Decimal("0.05"),
        )
    )

    assert decision.decision == "NO_TRADE"
    assert decision.reason == "PRICE_GAP_TOO_SMALL"
    assert decision.price_gap == Decimal("0.01")
    assert decision.edge == Decimal("0.01")


@pytest.mark.asyncio
async def test_strategy_returns_no_trade_when_spread_too_high() -> None:
    decision = await StrategyEngine().evaluate(
        _context(up_ask=Decimal("0.90"), down_ask=Decimal("0.11"), up_spread=Decimal("0.08"), max_spread=Decimal("0.02"))
    )

    assert decision.decision == "NO_TRADE"
    assert decision.reason == "SPREAD_TOO_HIGH"
    assert decision.spread == Decimal("0.08")


@pytest.mark.asyncio
async def test_strategy_returns_orderbook_data_missing_when_ask_missing() -> None:
    decision = await StrategyEngine().evaluate(_context(up_ask=None))

    assert decision.decision == "NO_TRADE"
    assert decision.reason == "ORDERBOOK_DATA_MISSING"


@pytest.mark.asyncio
async def test_strategy_returns_no_trade_when_market_data_stale() -> None:
    decision = await StrategyEngine().evaluate(
        _context(market_data_age_seconds=Decimal("6"), max_data_age_seconds=5)
    )

    assert decision.decision == "NO_TRADE"
    assert decision.reason == "MARKET_DATA_STALE"


@pytest.mark.asyncio
async def test_strategy_does_not_require_chainlink_prices() -> None:
    decision = await StrategyEngine().evaluate(
        _context(
            btc_start_price=None,
            btc_current_price=None,
            chainlink_data_age_seconds=None,
            up_ask=Decimal("0.90"),
            down_ask=Decimal("0.11"),
        )
    )

    assert decision.decision == "BUY_UP"
    assert decision.delta is None


@pytest.mark.asyncio
async def test_paper_order_creation_persists_decision_and_filled_order(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    context = _context()
    decision = await StrategyEngine().evaluate(context)
    risk = await RiskManager().validate_for_paper_trade(decision, context)

    assert decision.decision == "BUY_UP"
    assert risk.passed

    async with sessionmaker() as session:
        market = _market()
        session.add(market)
        await session.commit()
        await session.refresh(market)

        persisted_decision = await persist_strategy_decision(session, market=market, decision=decision)
        order = await PaperTradingEngine().create_order(
            session,
            market=market,
            persisted_decision=persisted_decision,
            decision=decision,
            context=context,
        )
        await session.commit()

        assert order is not None
        rows = (await session.execute(select(StrategyDecision))).scalars().all()
        orders = (await session.execute(select(Order))).scalars().all()

        assert len(rows) == 1
        assert rows[0].decision == "BUY_UP"
        assert len(orders) == 1
        assert orders[0].mode == "paper"
        assert orders[0].status == "FILLED"
        assert orders[0].token_id == "up-token"
        assert orders[0].price == Decimal("0.90000000")
        assert orders[0].size_matched == orders[0].size
        assert orders[0].raw_response["simulated"] is True


def _context(**overrides) -> StrategyContext:
    values = {
        "market_id": 1,
        "event_slug": "btc-updown-15m-1782563400",
        "up_token_id": "up-token",
        "down_token_id": "down-token",
        "time_remaining_seconds": 120,
        "btc_start_price": None,
        "btc_current_price": None,
        "up_bid": Decimal("0.49"),
        "up_ask": Decimal("0.90"),
        "up_spread": Decimal("0.01"),
        "down_bid": Decimal("0.48"),
        "down_ask": Decimal("0.11"),
        "down_spread": Decimal("0.01"),
        "market_data_age_seconds": Decimal("1"),
        "chainlink_data_age_seconds": None,
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
    return StrategyContext(**values)


def _market() -> Market:
    return Market(
        event_slug="btc-updown-15m-1782563400",
        market_slug="btc-updown-15m-1782563400-market",
        condition_id="condition-1",
        question="BTC Up or Down",
        active=True,
        closed=False,
        start_ts=1782563400,
        end_ts=1782564300,
        up_token_id="up-token",
        down_token_id="down-token",
        raw_event={},
        raw_market={},
    )
