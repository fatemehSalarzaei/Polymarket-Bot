from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.markets import get_clob_client, get_gamma_client
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.tick import OrderbookSnapshot
from app.services.market_discovery import MarketDiscoveryService
from app.services.polymarket_clob import normalize_orderbook
from app.services.polymarket_errors import PolymarketHttpError


class FakeGammaClient:
    async def get_event_by_slug(self, slug: str) -> dict:
        return {
            "slug": slug,
            "active": True,
            "closed": False,
            "title": "BTC Up or Down",
            "markets": [
                {
                    "slug": f"{slug}-market",
                    "question": "Bitcoin Up or Down",
                    "conditionId": "condition-1",
                    "active": True,
                    "closed": False,
                    "outcomes": ["Up", "Down"],
                    "clobTokenIds": ["up-token", "down-token"],
                }
            ],
        }


class FakeClobClient:
    def __init__(self) -> None:
        self.token_ids: list[str] = []

    async def get_orderbook(self, token_id: str):
        self.token_ids.append(token_id)
        return normalize_orderbook(_orderbook_payload(token_id), fallback_token_id=token_id)


class TimeoutClobClient:
    async def get_orderbook(self, token_id: str):
        raise PolymarketHttpError(
            code="POLYMARKET_CLOB_TIMEOUT",
            message="timeout",
            endpoint="/book",
            technical_detail=f"timeout for {token_id}",
        )


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


def test_normalize_orderbook_computes_best_prices_midpoint_and_spread() -> None:
    dto = normalize_orderbook(_orderbook_payload("up-token"), fallback_token_id="up-token")

    assert dto.token_id == "up-token"
    assert dto.best_bid == Decimal("0.48")
    assert dto.best_ask == Decimal("0.51")
    assert dto.midpoint == Decimal("0.495")
    assert dto.spread == Decimal("0.03")
    assert dto.source_timestamp == datetime(2026, 6, 27, 12, 30, tzinfo=UTC)


def test_get_current_market_orderbook_persists_up_and_down_snapshots(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    fake_clob = FakeClobClient()
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_gamma_client] = lambda: FakeGammaClient()
    app.dependency_overrides[get_clob_client] = lambda: fake_clob

    try:
        with TestClient(app) as client:
            response = client.get("/api/markets/current/orderbook")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["up"]["token_id"] == "up-token"
    assert body["down"]["token_id"] == "down-token"
    assert body["up"]["best_bid"] == "0.48000000"
    assert body["up"]["best_ask"] == "0.51000000"
    assert fake_clob.token_ids == ["up-token", "down-token"]

    async def assert_snapshots_saved() -> None:
        async with sessionmaker() as session:
            snapshots = (await session.execute(select(OrderbookSnapshot).order_by(OrderbookSnapshot.outcome))).scalars().all()
            assert [snapshot.outcome for snapshot in snapshots] == ["DOWN", "UP"]
            assert {snapshot.token_id for snapshot in snapshots} == {"up-token", "down-token"}
            assert all(snapshot.spread is not None for snapshot in snapshots)

    import asyncio

    asyncio.run(assert_snapshots_saved())


def test_get_current_market_orderbook_returns_structured_timeout_when_no_cache(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_gamma_client] = lambda: FakeGammaClient()
    app.dependency_overrides[get_clob_client] = lambda: TimeoutClobClient()

    try:
        with TestClient(app) as client:
            response = client.get("/api/markets/current/orderbook")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["code"] == "POLYMARKET_CLOB_TIMEOUT"
    assert "httpx.ReadTimeout" not in response.text


def test_get_current_market_orderbook_serves_cached_snapshots_on_timeout(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    async def seed_cache() -> None:
        async with sessionmaker() as session:
            from app.models.market import Market

            start_ts = MarketDiscoveryService.compute_cycle_start(datetime.now(UTC))
            event_slug = MarketDiscoveryService.build_btc_15m_slug(start_ts)
            market = Market(
                event_slug=event_slug,
                market_slug=f"{event_slug}-market",
                condition_id="condition-1",
                question="BTC Up or Down",
                active=True,
                closed=False,
                start_ts=start_ts,
                end_ts=start_ts + 900,
                up_token_id="up-token",
                down_token_id="down-token",
                raw_event={},
                raw_market={},
            )
            session.add(market)
            await session.flush()
            session.add_all(
                [
                    OrderbookSnapshot(
                        market_id=market.id,
                        token_id="up-token",
                        outcome="UP",
                        best_bid="0.48",
                        best_ask="0.51",
                        midpoint="0.495",
                        spread="0.03",
                        bids=[],
                        asks=[],
                    ),
                    OrderbookSnapshot(
                        market_id=market.id,
                        token_id="down-token",
                        outcome="DOWN",
                        best_bid="0.46",
                        best_ask="0.53",
                        midpoint="0.495",
                        spread="0.07",
                        bids=[],
                        asks=[],
                    ),
                ]
            )
            await session.commit()

    asyncio.run(seed_cache())

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_gamma_client] = lambda: FakeGammaClient()
    app.dependency_overrides[get_clob_client] = lambda: TimeoutClobClient()

    try:
        with TestClient(app) as client:
            response = client.get("/api/markets/current/orderbook")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["up"]["best_ask"] == "0.51000000"
    assert response.json()["down"]["best_ask"] == "0.53000000"


def _orderbook_payload(token_id: str) -> dict:
    return {
        "market": "condition-1",
        "asset_id": token_id,
        "timestamp": 1782563400000,
        "hash": f"hash-{token_id}",
        "bids": [
            {"price": "0.46", "size": "100"},
            {"price": "0.48", "size": "75"},
        ],
        "asks": [
            {"price": "0.53", "size": "60"},
            {"price": "0.51", "size": "80"},
        ],
        "min_order_size": "5",
        "tick_size": "0.01",
        "neg_risk": False,
        "last_trade_price": "0.50",
    }
