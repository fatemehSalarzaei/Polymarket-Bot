from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.services.dashboard_broadcaster import DashboardBroadcaster
from app.services.order_reconciler import OrderReconciler


ConnectFactory = Callable[[str], Any]
SleepFn = Callable[[float], Awaitable[None]]


class UserWebSocketListener:
    def __init__(
        self,
        *,
        url: str,
        sessionmaker: async_sessionmaker[AsyncSession],
        broadcaster: DashboardBroadcaster,
        connect: ConnectFactory | None = None,
        sleep: SleepFn = asyncio.sleep,
        reconciler: OrderReconciler | None = None,
        max_backoff_seconds: float = 30,
    ) -> None:
        self.url = url
        self._sessionmaker = sessionmaker
        self._broadcaster = broadcaster
        self._connect = connect or websockets.connect
        self._sleep = sleep
        self._reconciler = reconciler or OrderReconciler()
        self._max_backoff_seconds = max_backoff_seconds
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
                    backoff = 1.0
                    async for raw_message in websocket:
                        for payload in _message_payloads(raw_message):
                            async with self._sessionmaker() as session:
                                order = await self._reconciler.apply_user_update(session, payload)
                                await session.commit()
                            if order is not None:
                                await self._broadcaster.broadcast("order_update", payload, freshness_key="user_ws")
                            handled += 1
                            if max_messages is not None and handled >= max_messages:
                                return
            except Exception:
                self.reconnect_attempts += 1
                await self._sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_seconds)


def _message_payloads(raw_message: Any) -> list[dict[str, Any]]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode()
    parsed = json.loads(raw_message) if isinstance(raw_message, str) else raw_message
    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("User websocket message list must contain objects")
        return parsed
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError("User websocket message must be an object or object array")

