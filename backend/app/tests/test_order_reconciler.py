from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.market import Market
from app.models.order import Order
from app.services.order_reconciler import OrderReconciler
from app.tasks.order_tasks import reconcile_open_real_orders_job, reconcile_open_real_orders_task


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
async def test_order_reconciler_updates_matched_size_and_status(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market = _market()
        session.add(market)
        await session.flush()
        order = _order(market)
        session.add(order)
        await session.flush()

        updated = await OrderReconciler().apply_user_update(
            session,
            {
                "order_id": "order-1",
                "status": "partially_matched",
                "filled_size": "2.5",
                "api_secret": "must-not-leak",
            },
        )

    assert updated is not None
    assert updated.status == "PARTIALLY_FILLED"
    assert updated.size_matched == Decimal("2.5")
    assert updated.raw_response["last_reconciliation"]["api_secret"] == "[redacted]"


@pytest.mark.asyncio
async def test_order_reconciler_sets_filled_at(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        market = _market()
        session.add(market)
        await session.flush()
        order = _order(market)
        session.add(order)
        await session.flush()

        updated = await OrderReconciler().apply_user_update(session, {"order_id": "order-1", "status": "filled", "size_matched": "5"})

    assert updated is not None
    assert updated.status == "FILLED"
    assert updated.filled_at is not None


@pytest.mark.asyncio
async def test_reconcile_open_real_orders_task_uses_backend_reconciler(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    assert reconcile_open_real_orders_task.name == "app.tasks.orders.reconcile_open_real_orders"

    async with sessionmaker() as session:
        market = _market()
        session.add(market)
        await session.flush()
        order = _order(market)
        session.add(order)
        await session.commit()

    result = await reconcile_open_real_orders_job(sessionmaker=sessionmaker, reconciler=FakeReconciler())

    assert result["reconciled"] == 1
    assert result["orders"][0]["status"] == "FILLED"
    assert result["orders"][0]["size_matched"] == "5.00000000"


class FakeReconciler:
    async def reconcile_open_real_orders(self, session: AsyncSession):
        from sqlalchemy import select

        order = (await session.execute(select(Order))).scalar_one()
        order.status = "FILLED"
        order.size_matched = Decimal("5")
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return [order]


def _market() -> Market:
    return Market(
        event_slug="btc-updown-reconcile",
        market_slug="btc-updown-reconcile",
        condition_id="condition-reconcile",
        question="BTC Up or Down",
        active=True,
        closed=False,
        up_token_id="up",
        down_token_id="down",
        raw_event={},
        raw_market={},
    )


def _order(market: Market) -> Order:
    return Order(
        market_id=market.id,
        mode="real",
        external_order_id="order-1",
        token_id=market.up_token_id,
        outcome="UP",
        side="BUY",
        order_type="FAK",
        price=Decimal("0.50"),
        size=Decimal("5"),
        size_matched=Decimal("0"),
        status="SUBMITTED",
        raw_response={},
    )
