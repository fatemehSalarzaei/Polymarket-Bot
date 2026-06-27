from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.routes.markets import get_gamma_client
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.models.market import Market
from app.services.market_discovery import MarketDiscoveryService, TokenMappingError


class FakeGammaClient:
    def __init__(self, event: dict) -> None:
        self.event = event
        self.requested_slug: str | None = None

    async def get_event_by_slug(self, slug: str) -> dict:
        self.requested_slug = slug
        return {**self.event, "slug": slug}


@pytest.fixture()
async def sessionmaker(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield maker
    await engine.dispose()


def test_compute_cycle_start_floor_at_boundary() -> None:
    now = datetime(2026, 6, 27, 12, 30, 0, tzinfo=UTC)

    assert MarketDiscoveryService.compute_cycle_start(now) == int(now.timestamp())


def test_compute_cycle_start_floors_inside_cycle() -> None:
    now = datetime(2026, 6, 27, 12, 44, 59, tzinfo=UTC)
    expected = int(datetime(2026, 6, 27, 12, 30, 0, tzinfo=UTC).timestamp())

    assert MarketDiscoveryService.compute_cycle_start(now) == expected


def test_compute_cycle_start_handles_naive_datetime_as_utc() -> None:
    now = datetime(2026, 6, 27, 12, 45, 1)
    expected = int(datetime(2026, 6, 27, 12, 45, 0, tzinfo=UTC).timestamp())

    assert MarketDiscoveryService.compute_cycle_start(now) == expected


def test_build_btc_15m_slug() -> None:
    assert MarketDiscoveryService.build_btc_15m_slug(1782563400) == "btc-updown-15m-1782563400"


def test_map_outcome_tokens_by_verified_index() -> None:
    market = {"outcomes": ["Up", "Down"], "clobTokenIds": ["up-token", "down-token"]}

    assert MarketDiscoveryService.map_outcome_tokens(market) == {
        "UP": "up-token",
        "DOWN": "down-token",
    }


def test_map_outcome_tokens_accepts_json_string_arrays() -> None:
    market = {"outcomes": '["Down", "Up"]', "clobTokenIds": '["down-token", "up-token"]'}

    assert MarketDiscoveryService.map_outcome_tokens(market) == {
        "UP": "up-token",
        "DOWN": "down-token",
    }


@pytest.mark.parametrize(
    "market",
    [
        {"outcomes": ["Up", "Up"], "clobTokenIds": ["a", "b"]},
        {"outcomes": ["Up", "Down"], "clobTokenIds": ["a"]},
        {"outcomes": ["Yes", "No"], "clobTokenIds": ["a", "b"]},
        {"outcomes": "not-json", "clobTokenIds": ["a", "b"]},
    ],
)
def test_ambiguous_token_mapping_fails(market: dict) -> None:
    with pytest.raises(TokenMappingError):
        MarketDiscoveryService.map_outcome_tokens(market)


def test_parse_event_validates_and_normalizes_market() -> None:
    event = _event_fixture("btc-updown-15m-1782563400")

    dto = MarketDiscoveryService.parse_event(event, expected_slug=event["slug"], start_ts=1782563400)

    assert dto.event_slug == "btc-updown-15m-1782563400"
    assert dto.condition_id == "condition-1"
    assert dto.up_token_id == "up-token"
    assert dto.down_token_id == "down-token"
    assert dto.start_ts == 1782563400


def test_get_current_market_persists_market(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    fake_gamma = FakeGammaClient(_event_fixture("btc-updown-15m-1782563400"))

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_gamma_client] = lambda: fake_gamma

    try:
        with TestClient(app) as client:
            response = client.get("/api/markets/current")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["event_slug"].startswith("btc-updown-15m-")
    assert body["up_token_id"] == "up-token"
    assert body["down_token_id"] == "down-token"
    assert fake_gamma.requested_slug == body["event_slug"]

    async def assert_market_saved() -> None:
        async with sessionmaker() as session:
            saved = (await session.execute(select(Market))).scalar_one()
            assert saved.event_slug == body["event_slug"]
            assert saved.condition_id == "condition-1"

    import asyncio

    asyncio.run(assert_market_saved())


def _event_fixture(slug: str) -> dict:
    return {
        "slug": slug,
        "active": True,
        "closed": False,
        "title": "BTC Up or Down",
        "markets": [
            {
                "slug": f"{slug}-market",
                "question": "Bitcoin Up or Down - June 27",
                "conditionId": "condition-1",
                "active": True,
                "closed": False,
                "outcomes": ["Up", "Down"],
                "clobTokenIds": ["up-token", "down-token"],
            }
        ],
    }
