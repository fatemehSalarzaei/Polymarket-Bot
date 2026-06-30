from __future__ import annotations

import pytest

from app.models.market import Market
from app.services.polymarket_resolution import PolymarketResolutionClient


class FakeGammaClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def get_event_by_slug(self, event_slug: str) -> dict:
        return self.payload


@pytest.mark.asyncio
async def test_official_resolution_requires_closed_resolved_single_winner() -> None:
    resolution = await PolymarketResolutionClient(
        FakeGammaClient(
            {
                "closed": True,
                "markets": [
                    {
                        "conditionId": "condition-1",
                        "closed": True,
                        "umaResolutionStatus": "resolved",
                        "outcomes": '["Up", "Down"]',
                        "outcomePrices": '["1", "0"]',
                    }
                ],
            }
        )
    ).get_official_resolution(_market())

    assert resolution.official is True
    assert resolution.status == "official"
    assert resolution.winning_outcome == "UP"


@pytest.mark.asyncio
async def test_official_resolution_rejects_open_market_even_with_prices() -> None:
    resolution = await PolymarketResolutionClient(
        FakeGammaClient(
            {
                "closed": True,
                "markets": [
                    {
                        "conditionId": "condition-1",
                        "closed": False,
                        "umaResolutionStatus": "resolved",
                        "outcomes": ["Up", "Down"],
                        "outcomePrices": ["1", "0"],
                    }
                ],
            }
        )
    ).get_official_resolution(_market())

    assert resolution.official is False
    assert resolution.status == "official_missing"
    assert resolution.reason == "MARKET_NOT_CLOSED"


@pytest.mark.asyncio
async def test_official_resolution_rejects_ambiguous_winner() -> None:
    resolution = await PolymarketResolutionClient(
        FakeGammaClient(
            {
                "closed": True,
                "markets": [
                    {
                        "conditionId": "condition-1",
                        "closed": True,
                        "umaResolutionStatus": "resolved",
                        "outcomes": ["Up", "Down"],
                        "outcomePrices": ["1", "1"],
                    }
                ],
            }
        )
    ).get_official_resolution(_market())

    assert resolution.official is False
    assert resolution.reason == "OFFICIAL_WINNING_OUTCOME_NOT_AVAILABLE"


def _market() -> Market:
    return Market(
        event_slug="btc-updown-15m-test",
        market_slug="btc-updown-15m-test",
        condition_id="condition-1",
        question="BTC Up or Down",
        active=False,
        closed=True,
        raw_event={},
        raw_market={},
    )
