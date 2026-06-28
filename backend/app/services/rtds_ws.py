from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import websockets

from app.schemas.websocket import BtcPriceTick
from app.services.dashboard_broadcaster import DashboardBroadcaster
from app.services.dashboard_event_bus import publish_dashboard_event


ConnectFactory = Callable[[str], Any]
SleepFn = Callable[[float], Awaitable[None]]
TickHandler = Callable[[BtcPriceTick], Awaitable[None]]


class RTDSWebSocketService:
    def __init__(
        self,
        *,
        url: str,
        broadcaster: DashboardBroadcaster,
        connect: ConnectFactory | None = None,
        sleep: SleepFn = asyncio.sleep,
        max_backoff_seconds: float = 30,
        on_tick: TickHandler | None = None,
    ) -> None:
        self.url = url
        self.broadcaster = broadcaster
        self._connect = connect or websockets.connect
        self._sleep = sleep
        self._max_backoff_seconds = max_backoff_seconds
        self._on_tick = on_tick
        self.reconnect_attempts = 0

    async def run(self, *, max_messages: int | None = None, max_attempts: int | None = None) -> None:
        handled = 0
        attempts = 0
        backoff = 1.0

        while max_messages is None or handled < max_messages:
            if max_attempts is not None and attempts >= max_attempts:
                return
            attempts += 1

            try:
                async with self._connect(self.url) as websocket:
                    await self._broadcast_status("connected")
                    await websocket.send(json.dumps(_subscription_message()))
                    await self._broadcast_status("subscribed")
                    ping_task = asyncio.create_task(_ping_loop(websocket, self._sleep))
                    backoff = 1.0
                    try:
                        async for raw_message in websocket:
                            for payload in _message_payloads(raw_message):
                                tick = parse_btc_price_tick(payload)
                                if self._on_tick is not None:
                                    await self._on_tick(tick)
                                await self.broadcaster.broadcast("btc_price_tick", tick, freshness_key="rtds_btc")
                                await publish_dashboard_event("btc_price_tick", tick, freshness_key="rtds_btc")
                                await self._broadcast_status("connected", last_tick_received_at=tick.received_at)
                                handled += 1
                                if max_messages is not None and handled >= max_messages:
                                    return
                    finally:
                        ping_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ping_task
            except Exception:
                self.reconnect_attempts += 1
                await self._broadcast_status("reconnecting")
                await self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_seconds)

        await self._broadcast_status("disconnected")

    async def _broadcast_status(self, status: str, *, last_tick_received_at: datetime | None = None) -> None:
        payload = {
            "status": status,
            "last_tick_received_at": last_tick_received_at,
            "subscribed_symbol": "btc/usd",
            "reconnect_attempts": self.reconnect_attempts,
            "timestamp": datetime.now(UTC),
        }
        await self.broadcaster.broadcast("rtds_status", payload)
        await publish_dashboard_event("rtds_status", payload)


def parse_btc_price_tick(payload: dict[str, Any]) -> BtcPriceTick:
    data = _extract_data_object(payload)
    symbol = str(data.get("symbol") or payload.get("symbol") or "btc/usd").lower()
    value = _required_decimal(data.get("value") or data.get("price") or data.get("answer"))
    source_timestamp = _parse_timestamp(data.get("timestamp") or data.get("updatedAt") or payload.get("timestamp"))

    return BtcPriceTick(
        symbol=symbol,
        value=value,
        source_timestamp=source_timestamp,
        received_at=datetime.now(UTC),
        raw_payload=payload,
    )


def _subscription_message() -> dict[str, Any]:
    return {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": json.dumps({"symbol": "btc/usd"}),
            }
        ],
    }


async def _ping_loop(websocket: Any, sleep: SleepFn) -> None:
    while True:
        await sleep(5)
        ping = getattr(websocket, "ping", None)
        if callable(ping):
            result = ping()
            if asyncio.iscoroutine(result):
                await result
        else:
            await websocket.send("PING")


def _extract_data_object(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("data", "payload", "value"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return payload


def _message_payloads(raw_message: Any) -> list[dict[str, Any]]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode()
    if isinstance(raw_message, str):
        parsed = json.loads(raw_message)
    else:
        parsed = raw_message

    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("RTDS websocket message list must contain objects")
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError("RTDS websocket message must be an object or object array")


def _required_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        raise ValueError("BTC price payload is missing value")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid decimal value: {value}") from None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, tz=UTC)
    if isinstance(value, str):
        if value.isdigit():
            return _parse_timestamp(int(value))
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None
