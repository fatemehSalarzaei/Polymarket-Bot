from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocket


class FreshnessTracker:
    def __init__(self) -> None:
        self._updated_at: dict[str, datetime] = {}

    def mark(self, key: str, at: datetime | None = None) -> datetime:
        timestamp = at or datetime.now(UTC)
        self._updated_at[key] = timestamp
        return timestamp

    def age_seconds(self, key: str, now: datetime | None = None) -> float | None:
        updated_at = self._updated_at.get(key)
        if updated_at is None:
            return None
        current = now or datetime.now(UTC)
        return (current - updated_at).total_seconds()

    def is_fresh(self, key: str, *, max_age_seconds: int, now: datetime | None = None) -> bool:
        age = self.age_seconds(key, now=now)
        return age is not None and age <= max_age_seconds


class DashboardBroadcaster:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.latest_events: dict[str, dict[str, Any]] = {}
        self.freshness = FreshnessTracker()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.add(websocket)

        for event in self.latest_events.values():
            await websocket.send_json(event)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(websocket)

    async def broadcast(self, event_type: str, data: Any, *, freshness_key: str | None = None) -> dict[str, Any]:
        if freshness_key is not None:
            self.freshness.mark(freshness_key)

        event = {
            "type": event_type,
            "data": jsonable_encoder(data),
        }
        self.latest_events[event_type] = event

        async with self._lock:
            clients = list(self._clients)

        stale_clients: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(event)
            except RuntimeError:
                stale_clients.append(client)

        if stale_clients:
            async with self._lock:
                for client in stale_clients:
                    self._clients.discard(client)

        return event


dashboard_broadcaster = DashboardBroadcaster()

