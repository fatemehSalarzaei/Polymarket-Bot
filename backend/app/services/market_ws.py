from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import websockets

from app.schemas.websocket import MarketTick
from app.services.dashboard_broadcaster import DashboardBroadcaster


ConnectFactory = Callable[[str], Any]
SleepFn = Callable[[float], Awaitable[None]]


class MarketWebSocketService:
    def __init__(
        self,
        *,
        url: str,
        broadcaster: DashboardBroadcaster,
        connect: ConnectFactory | None = None,
        sleep: SleepFn = asyncio.sleep,
        max_backoff_seconds: float = 30,
    ) -> None:
        self.url = url
        self.broadcaster = broadcaster
        self._connect = connect or websockets.connect
        self._sleep = sleep
        self._max_backoff_seconds = max_backoff_seconds
        self.reconnect_attempts = 0

    async def run(
        self,
        *,
        asset_ids: list[str],
        max_messages: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        handled = 0
        attempts = 0
        backoff = 1.0

        while max_messages is None or handled < max_messages:
            if max_attempts is not None and attempts >= max_attempts:
                return
            attempts += 1

            try:
                async with self._connect(self.url) as websocket:
                    await websocket.send(json.dumps({"assets_ids": asset_ids, "type": "market"}))
                    backoff = 1.0
                    async for raw_message in websocket:
                        for payload in _message_payloads(raw_message):
                            tick = parse_market_tick(payload)
                            await self.broadcaster.broadcast("market_tick", tick, freshness_key="market_ws")
                            handled += 1
                            if max_messages is not None and handled >= max_messages:
                                return
            except Exception:
                self.reconnect_attempts += 1
                await self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_seconds)


def parse_market_tick(payload: dict[str, Any]) -> MarketTick:
    token_id = str(payload.get("asset_id") or payload.get("token_id") or payload.get("assetId") or "")
    if not token_id:
        raise ValueError("Market websocket payload is missing token id")

    best_bid = _maybe_decimal(payload.get("best_bid") or payload.get("bestBid"))
    best_ask = _maybe_decimal(payload.get("best_ask") or payload.get("bestAsk"))
    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None

    return MarketTick(
        token_id=token_id,
        event_type=_maybe_str(payload.get("event_type") or payload.get("type")),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        raw_payload=payload,
        received_at=datetime.now(UTC),
    )


def _message_payloads(raw_message: Any) -> list[dict[str, Any]]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode()
    if isinstance(raw_message, str):
        parsed = json.loads(raw_message)
    else:
        parsed = raw_message

    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("Market websocket message list must contain objects")
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError("Market websocket message must be an object or object array")


def _maybe_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid decimal value: {value}") from None


def _maybe_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

