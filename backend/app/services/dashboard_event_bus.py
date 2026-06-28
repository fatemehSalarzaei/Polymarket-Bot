from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis
from fastapi.encoders import jsonable_encoder

from app.core.config import get_settings


logger = logging.getLogger(__name__)

DASHBOARD_EVENTS_CHANNEL = "dashboard.events"
SECRET_KEY_MARKERS = (
    "private_key",
    "api_secret",
    "api_passphrase",
    "passphrase",
    "secret",
    "seed",
    "mnemonic",
)

DashboardEventCallback = Callable[[str, Any, str | None], Awaitable[None] | None]


async def publish_dashboard_event(
    event_type: str,
    data: Any,
    freshness_key: str | None = None,
    *,
    redis_client: redis.Redis | None = None,
) -> dict[str, Any]:
    event = _build_event(event_type, data, freshness_key)
    owns_client = redis_client is None
    client = redis_client or _redis_client()
    try:
        try:
            await client.publish(DASHBOARD_EVENTS_CHANNEL, json.dumps(event, separators=(",", ":"), default=str))
        except Exception:
            logger.exception("dashboard_event_bus_publish_failed", extra={"event_type": event_type})
    finally:
        if owns_client:
            await _close_redis_resource(client)
    return event


async def subscribe_dashboard_events(
    callback: DashboardEventCallback,
    *,
    redis_client: redis.Redis | None = None,
    reconnect_delay_seconds: float = 1.0,
) -> None:
    owns_client = redis_client is None
    client = redis_client or _redis_client()
    try:
        while True:
            pubsub = client.pubsub()
            try:
                await pubsub.subscribe(DASHBOARD_EVENTS_CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    event = _parse_event(message.get("data"))
                    result = callback(event["type"], event["data"], event.get("freshness_key"))
                    if inspect.isawaitable(result):
                        await result
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("dashboard_event_bus_subscribe_failed")
                await asyncio.sleep(reconnect_delay_seconds)
            finally:
                await _close_redis_resource(pubsub)
    finally:
        if owns_client:
            await _close_redis_resource(client)


def _redis_client() -> redis.Redis:
    return redis.from_url(
        str(get_settings().redis_url),
        decode_responses=True,
        socket_connect_timeout=0.2,
    )


async def _close_redis_resource(resource: Any) -> None:
    close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def _build_event(event_type: str, data: Any, freshness_key: str | None) -> dict[str, Any]:
    return {
        "type": event_type,
        "data": _sanitize_for_dashboard(jsonable_encoder(data)),
        "freshness_key": freshness_key,
    }


def _parse_event(raw_data: Any) -> dict[str, Any]:
    parsed = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
    if not isinstance(parsed, dict) or not isinstance(parsed.get("type"), str):
        raise ValueError("Dashboard event bus message must contain a string type")
    return {
        "type": parsed["type"],
        "data": _sanitize_for_dashboard(parsed.get("data")),
        "freshness_key": parsed.get("freshness_key"),
    }


def _sanitize_for_dashboard(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _looks_secret(key_text):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = _sanitize_for_dashboard(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_dashboard(item) for item in value]
    return value


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)
