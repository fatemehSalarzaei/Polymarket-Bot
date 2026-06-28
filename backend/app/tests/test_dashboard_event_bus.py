from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.services.dashboard_broadcaster import DashboardBroadcaster
from app.services.dashboard_event_bus import DASHBOARD_EVENTS_CHANNEL, publish_dashboard_event, subscribe_dashboard_events


class FakeRedis:
    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self.published: list[tuple[str, str]] = []
        self._messages = messages or []
        self.closed = False

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))

    def pubsub(self) -> "FakePubSub":
        return FakePubSub(self._messages)

    async def aclose(self) -> None:
        self.closed = True


class FakePubSub:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.subscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def listen(self):
        for message in self.messages:
            yield message

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_publish_dashboard_event_serializes_and_redacts_secrets() -> None:
    redis = FakeRedis()

    event = await publish_dashboard_event(
        "order_update",
        {"order_id": "1", "private_key": "super-secret", "nested": {"api_secret": "also-secret"}},
        freshness_key="user_ws",
        redis_client=redis,
    )

    channel, raw_message = redis.published[0]
    payload = json.loads(raw_message)

    assert channel == DASHBOARD_EVENTS_CHANNEL
    assert event["data"]["private_key"] == "[REDACTED]"
    assert payload["data"]["private_key"] == "[REDACTED]"
    assert payload["data"]["nested"]["api_secret"] == "[REDACTED]"
    assert "super-secret" not in raw_message


@pytest.mark.asyncio
async def test_subscribe_dashboard_events_forwards_to_broadcaster() -> None:
    broadcaster = DashboardBroadcaster()
    raw_event = json.dumps({"type": "btc_price_tick", "data": {"value": "61000"}, "freshness_key": "rtds_btc"})
    redis = FakeRedis([{"type": "message", "data": raw_event}])

    async def callback(event_type: str, data: Any, freshness_key: str | None) -> None:
        await broadcaster.broadcast(event_type, data, freshness_key=freshness_key)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await subscribe_dashboard_events(callback, redis_client=redis)

    assert broadcaster.latest_events["btc_price_tick"]["data"] == {"value": "61000"}
    assert broadcaster.freshness.is_fresh("rtds_btc", max_age_seconds=5)
