from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import websockets

from app.core.errors import error_payload
from app.schemas.websocket import MarketTick
from app.services.dashboard_broadcaster import DashboardBroadcaster
from app.services.dashboard_event_bus import publish_dashboard_event


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
        self._top_of_book: dict[str, MarketTick] = {}

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
                await self._broadcast_status("connected", asset_ids=asset_ids)
                async with self._connect(self.url) as websocket:
                    await websocket.send(
                        json.dumps(
                            {
                                "assets_ids": asset_ids,
                                "type": "market",
                                "custom_feature_enabled": True,
                            }
                        )
                    )
                    backoff = 1.0
                    async for raw_message in websocket:
                        for payload in _message_payloads(raw_message):
                            try:
                                events = parse_market_events(payload, previous=self._top_of_book)
                            except ValueError as exc:
                                payload = error_payload("ORDERBOOK_PARSE_ERROR", technical_detail=str(exc))
                                await self.broadcaster.broadcast("error", payload)
                                await publish_dashboard_event("error", payload)
                                raise
                            for event_type, event_data in events:
                                if event_type == "market_tick":
                                    assert isinstance(event_data, MarketTick)
                                    self._top_of_book[event_data.token_id] = event_data
                                    await self.broadcaster.broadcast(
                                        "market_tick",
                                        event_data,
                                        freshness_key="market_ws",
                                    )
                                    await publish_dashboard_event(
                                        "market_tick",
                                        event_data,
                                        freshness_key="market_ws",
                                    )
                                else:
                                    await self.broadcaster.broadcast(event_type, event_data, freshness_key="market_ws")
                                    await publish_dashboard_event(event_type, event_data, freshness_key="market_ws")
                            handled += 1
                            if max_messages is not None and handled >= max_messages:
                                return
            except Exception:
                self.reconnect_attempts += 1
                await self._broadcast_status("reconnecting", asset_ids=asset_ids)
                await self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_seconds)

        await self._broadcast_status("disconnected", asset_ids=asset_ids)

    async def _broadcast_status(self, status: str, *, asset_ids: list[str]) -> None:
        payload = {
            "status": status,
            "asset_ids": asset_ids,
            "reconnect_attempts": self.reconnect_attempts,
            "timestamp": datetime.now(UTC),
        }
        await self.broadcaster.broadcast("market_ws_status", payload)
        await publish_dashboard_event("market_ws_status", payload)


def parse_market_tick(payload: dict[str, Any]) -> MarketTick:
    events = parse_market_events(payload)
    for event_type, event_data in events:
        if event_type == "market_tick":
            assert isinstance(event_data, MarketTick)
            return event_data
    raise ValueError("Market websocket payload did not contain a market tick")


def parse_market_events(
    payload: dict[str, Any],
    *,
    previous: dict[str, MarketTick] | None = None,
) -> list[tuple[str, Any]]:
    event_type = _maybe_str(payload.get("event_type") or payload.get("type")) or "unknown"
    previous = previous or {}

    if event_type == "book":
        tick = _parse_book_event(payload)
        snapshot = {
            "token_id": tick.token_id,
            "event_type": "book",
            "best_bid": tick.best_bid,
            "best_ask": tick.best_ask,
            "midpoint": tick.midpoint,
            "spread": tick.spread,
            "last_trade_price": tick.last_trade_price,
            "bids": _levels_from_payload(payload.get("bids") or payload.get("buys") or []),
            "asks": _levels_from_payload(payload.get("asks") or payload.get("sells") or []),
            "received_at": tick.received_at,
            "data_source": tick.data_source,
            "raw_payload": payload,
        }
        return [("market_tick", tick), ("orderbook_snapshot", snapshot)]

    if event_type == "price_change":
        events: list[tuple[str, Any]] = []
        changes = payload.get("price_changes") or payload.get("changes")
        if changes is None:
            changes = [payload]
        if not isinstance(changes, list):
            raise ValueError("price_change payload must contain price_changes list")
        for item in changes:
            if not isinstance(item, dict):
                continue
            tick = _parse_top_of_book_event({**payload, **item, "event_type": "price_change"}, previous=previous)
            events.append(("market_tick", tick))
        return events

    if event_type == "best_bid_ask":
        return [("market_tick", _parse_top_of_book_event(payload, previous=previous))]

    if event_type == "last_trade_price":
        tick = _parse_last_trade_event(payload, previous=previous)
        return [("market_tick", tick), ("trade_tick", tick)]

    if event_type == "tick_size_change":
        token_id = str(payload.get("asset_id") or payload.get("token_id") or payload.get("assetId") or "")
        return [
            (
                "market_ws_status",
                {
                    "status": "tick_size_change",
                    "token_id": token_id,
                    "tick_size": payload.get("new_tick_size") or payload.get("tick_size"),
                    "message": "Polymarket tick size changed; order placement may fail if settings are stale.",
                    "timestamp": datetime.now(UTC),
                },
            )
        ]

    return [("market_tick", _parse_top_of_book_event(payload, previous=previous))]


def _parse_book_event(payload: dict[str, Any]) -> MarketTick:
    token_id = str(payload.get("asset_id") or payload.get("token_id") or payload.get("assetId") or "")
    if not token_id:
        raise ValueError("Market websocket payload is missing token id")

    bids = _levels_from_payload(payload.get("bids") or payload.get("buys") or [])
    asks = _levels_from_payload(payload.get("asks") or payload.get("sells") or [])
    best_bid = max((level["price"] for level in bids), default=None)
    best_ask = min((level["price"] for level in asks), default=None)
    spread = _spread(best_bid, best_ask)
    midpoint = _midpoint(best_bid, best_ask)

    return MarketTick(
        token_id=token_id,
        event_type="book",
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=midpoint,
        spread=spread,
        last_trade_price=_maybe_decimal(payload.get("last_trade_price") or payload.get("lastTradePrice")),
        data_source="market_ws",
        raw_payload=payload,
        received_at=datetime.now(UTC),
    )


def _parse_top_of_book_event(payload: dict[str, Any], *, previous: dict[str, MarketTick]) -> MarketTick:
    token_id = str(payload.get("asset_id") or payload.get("token_id") or payload.get("assetId") or "")
    if not token_id:
        raise ValueError("Market websocket payload is missing token id")
    prior = previous.get(token_id)
    best_bid = _maybe_decimal(payload.get("best_bid") or payload.get("bestBid")) or (prior.best_bid if prior else None)
    best_ask = _maybe_decimal(payload.get("best_ask") or payload.get("bestAsk")) or (prior.best_ask if prior else None)
    spread = _maybe_decimal(payload.get("spread")) or _spread(best_bid, best_ask)
    return MarketTick(
        token_id=token_id,
        event_type=_maybe_str(payload.get("event_type") or payload.get("type")),
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=_midpoint(best_bid, best_ask),
        spread=spread,
        last_trade_price=prior.last_trade_price if prior else None,
        data_source="market_ws",
        raw_payload=payload,
        received_at=datetime.now(UTC),
    )


def _parse_last_trade_event(payload: dict[str, Any], *, previous: dict[str, MarketTick]) -> MarketTick:
    token_id = str(payload.get("asset_id") or payload.get("token_id") or payload.get("assetId") or "")
    if not token_id:
        raise ValueError("Market websocket payload is missing token id")
    prior = previous.get(token_id)
    return MarketTick(
        token_id=token_id,
        event_type="last_trade_price",
        best_bid=prior.best_bid if prior else None,
        best_ask=prior.best_ask if prior else None,
        midpoint=_midpoint(prior.best_bid, prior.best_ask) if prior else None,
        spread=prior.spread if prior else None,
        last_trade_price=_maybe_decimal(payload.get("price") or payload.get("last_trade_price") or payload.get("lastTradePrice")),
        data_source="market_ws",
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


def _levels_from_payload(value: Any) -> list[dict[str, Decimal]]:
    if not isinstance(value, list):
        return []
    levels: list[dict[str, Decimal]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        price = _maybe_decimal(item.get("price") or item.get("p"))
        size = _maybe_decimal(item.get("size") or item.get("s"))
        if price is not None and size is not None:
            levels.append({"price": price, "size": size})
    return levels


def _spread(best_bid: Decimal | None, best_ask: Decimal | None) -> Decimal | None:
    if best_bid is None or best_ask is None:
        return None
    return best_ask - best_bid


def _midpoint(best_bid: Decimal | None, best_ask: Decimal | None) -> Decimal | None:
    if best_bid is None or best_ask is None:
        return None
    return (best_bid + best_ask) / Decimal("2")
