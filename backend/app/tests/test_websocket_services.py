import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.services.dashboard_broadcaster import DashboardBroadcaster, dashboard_broadcaster
from app.services.market_ws import MarketWebSocketService, parse_market_tick
from app.services.rtds_ws import RTDSWebSocketService, parse_btc_price_tick


class FakeWebSocketConnection:
    def __init__(self, messages: list[Any] | None = None, *, fail_on_iter: bool = False) -> None:
        self.messages = messages or []
        self.fail_on_iter = fail_on_iter
        self.sent: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send(self, message: str) -> None:
        self.sent.append(message)

    def __aiter__(self):
        self._iterator = iter(self.messages)
        return self

    async def __anext__(self):
        if self.fail_on_iter:
            raise ConnectionError("mock disconnect")
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


def test_dashboard_ws_sends_latest_event_on_connect() -> None:
    dashboard_broadcaster.latest_events.clear()

    asyncio.run(dashboard_broadcaster.broadcast("bot_status", {"running": False}))

    with TestClient(app) as client:
        with client.websocket_connect("/ws/dashboard") as websocket:
            assert websocket.receive_json() == {
                "type": "bot_status",
                "data": {"running": False},
            }


def test_freshness_tracker_marks_and_expires() -> None:
    broadcaster = DashboardBroadcaster()
    marked_at = datetime(2026, 6, 27, 12, 30, tzinfo=UTC)

    broadcaster.freshness.mark("market_ws", marked_at)

    assert broadcaster.freshness.is_fresh(
        "market_ws",
        max_age_seconds=5,
        now=marked_at + timedelta(seconds=4),
    )
    assert not broadcaster.freshness.is_fresh(
        "market_ws",
        max_age_seconds=5,
        now=marked_at + timedelta(seconds=6),
    )


def test_parse_market_tick_normalizes_prices() -> None:
    tick = parse_market_tick(
        {
            "asset_id": "up-token",
            "event_type": "price_change",
            "best_bid": "0.48",
            "best_ask": "0.51",
        }
    )

    assert tick.token_id == "up-token"
    assert tick.best_bid == Decimal("0.48")
    assert tick.best_ask == Decimal("0.51")
    assert tick.spread == Decimal("0.03")


def test_market_ws_broadcasts_mock_message_and_tracks_freshness() -> None:
    broadcaster = DashboardBroadcaster()
    fake_connection = FakeWebSocketConnection(
        [
            json.dumps(
                {
                    "asset_id": "up-token",
                    "event_type": "price_change",
                    "best_bid": "0.48",
                    "best_ask": "0.51",
                }
            )
        ]
    )

    service = MarketWebSocketService(
        url="wss://example.test/market",
        broadcaster=broadcaster,
        connect=lambda url: fake_connection,
        sleep=_no_sleep,
    )

    asyncio.run(service.run(asset_ids=["up-token", "down-token"], max_messages=1))

    assert json.loads(fake_connection.sent[0]) == {
        "assets_ids": ["up-token", "down-token"],
        "type": "market",
    }
    assert broadcaster.latest_events["market_tick"]["data"]["token_id"] == "up-token"
    assert broadcaster.freshness.is_fresh("market_ws", max_age_seconds=5)


def test_market_ws_reconnects_with_backoff_after_disconnect() -> None:
    broadcaster = DashboardBroadcaster()
    sleep_calls: list[float] = []
    connections = [
        FakeWebSocketConnection(fail_on_iter=True),
        FakeWebSocketConnection([{"asset_id": "down-token", "best_bid": "0.44", "best_ask": "0.46"}]),
    ]

    def connect(_: str) -> FakeWebSocketConnection:
        return connections.pop(0)

    async def record_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    service = MarketWebSocketService(
        url="wss://example.test/market",
        broadcaster=broadcaster,
        connect=connect,
        sleep=record_sleep,
    )

    asyncio.run(service.run(asset_ids=["down-token"], max_messages=1, max_attempts=2))

    assert service.reconnect_attempts == 1
    assert sleep_calls == [1.0]
    assert broadcaster.latest_events["market_tick"]["data"]["token_id"] == "down-token"


def test_parse_btc_price_tick_from_mock_rtds_payload() -> None:
    tick = parse_btc_price_tick(
        {
            "topic": "crypto_prices_chainlink",
            "data": {
                "symbol": "btc/usd",
                "price": "61234.12",
                "timestamp": 1782563400000,
            },
        }
    )

    assert tick.symbol == "btc/usd"
    assert tick.value == Decimal("61234.12")
    assert tick.source_timestamp == datetime(2026, 6, 27, 12, 30, tzinfo=UTC)


def test_rtds_ws_broadcasts_mock_message_and_tracks_freshness() -> None:
    broadcaster = DashboardBroadcaster()
    fake_connection = FakeWebSocketConnection(
        [
            json.dumps(
                {
                    "topic": "crypto_prices_chainlink",
                    "data": {"symbol": "btc/usd", "price": "61234.12"},
                }
            )
        ]
    )

    service = RTDSWebSocketService(
        url="wss://example.test/rtds",
        broadcaster=broadcaster,
        connect=lambda url: fake_connection,
        sleep=_no_sleep,
    )

    asyncio.run(service.run(max_messages=1))

    subscription = json.loads(fake_connection.sent[0])
    assert subscription["action"] == "subscribe"
    assert subscription["subscriptions"][0]["topic"] == "crypto_prices_chainlink"
    assert broadcaster.latest_events["btc_price_tick"]["data"]["value"] == "61234.12"
    assert broadcaster.freshness.is_fresh("rtds_btc", max_age_seconds=5)


async def _no_sleep(_: float) -> None:
    return None

