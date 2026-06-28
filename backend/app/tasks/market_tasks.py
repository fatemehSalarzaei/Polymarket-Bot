from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.errors import error_payload
from app.db.session import get_sessionmaker
from app.models.market import Market
from app.schemas.market import MarketResponse
from app.schemas.orderbook import CurrentMarketOrderbookResponse
from app.services.market_discovery import MarketDiscoveryService, persist_active_market
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.orderbook import persist_orderbook_snapshot
from app.services.polymarket_clob import PolymarketClobClient
from app.services.polymarket_errors import PolymarketHttpError
from app.services.polymarket_gamma import PolymarketGammaClient

logger = logging.getLogger(__name__)
_ORDERBOOK_FETCH_IN_PROGRESS = False


@celery_app.task(name="app.tasks.market.discover_current_market")
def discover_current_market_task() -> dict[str, Any]:
    return asyncio.run(discover_current_market_job())


@celery_app.task(name="app.tasks.market.fetch_current_orderbook")
def fetch_current_orderbook_task() -> dict[str, Any]:
    return asyncio.run(fetch_current_orderbook_job())


async def discover_current_market_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    gamma_client: PolymarketGammaClient | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    service = MarketDiscoveryService(gamma_client or PolymarketGammaClient(str(settings.polymarket_gamma_host)))
    maker = sessionmaker or get_sessionmaker()
    async with maker() as session:
        dto = await service.discover_current_market()
        market = await persist_active_market(session, dto)
        logger.info("current_market_discovered", extra={"market_id": market.id, "event_slug": market.event_slug})
        await publish_dashboard_event(
            "current_market",
            MarketResponse.model_validate(market).model_dump(mode="json"),
            freshness_key="market_discovery",
        )
        return {"market_id": market.id, "event_slug": market.event_slug}


async def fetch_current_orderbook_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    clob_client: PolymarketClobClient | None = None,
) -> dict[str, Any]:
    global _ORDERBOOK_FETCH_IN_PROGRESS
    if _ORDERBOOK_FETCH_IN_PROGRESS:
        logger.warning("orderbook_fetch_skipped", extra={"reason": "ORDERBOOK_FETCH_ALREADY_RUNNING"})
        return {"persisted": 0, "reason": "ORDERBOOK_FETCH_ALREADY_RUNNING", "recoverable": True}
    _ORDERBOOK_FETCH_IN_PROGRESS = True
    try:
        return await _fetch_current_orderbook_job(sessionmaker=sessionmaker, clob_client=clob_client)
    finally:
        _ORDERBOOK_FETCH_IN_PROGRESS = False


async def _fetch_current_orderbook_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    clob_client: PolymarketClobClient | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    maker = sessionmaker or get_sessionmaker()
    client = clob_client or PolymarketClobClient(
        str(settings.polymarket_clob_host),
        read_timeout=5,
        max_retries=1,
    )

    async with maker() as session:
        market = await _current_market(session)
        if market is None:
            logger.warning("orderbook_fetch_skipped", extra={"reason": "CURRENT_MARKET_MISSING"})
            return {"persisted": 0, "reason": "CURRENT_MARKET_MISSING"}

        try:
            up_orderbook = await client.get_orderbook(market.up_token_id)
            down_orderbook = await client.get_orderbook(market.down_token_id)
        except PolymarketHttpError as exc:
            logger.warning(
                "orderbook_fetch_recoverable_polymarket_error",
                extra={"code": exc.code, "endpoint": exc.endpoint, "technical_detail": exc.technical_detail},
            )
            await publish_dashboard_event("error", error_payload(exc.code, technical_detail=exc.technical_detail))
            await publish_dashboard_event(
                "market_ws_status",
                {
                    "status": "rest_orderbook_error",
                    "message": exc.message,
                    "code": exc.code,
                    "endpoint": exc.endpoint,
                },
            )
            return {"persisted": 0, "reason": exc.code, "recoverable": True}
        up_snapshot = await persist_orderbook_snapshot(session, market=market, outcome="UP", orderbook=up_orderbook)
        down_snapshot = await persist_orderbook_snapshot(session, market=market, outcome="DOWN", orderbook=down_orderbook)
        await session.commit()
        logger.info("orderbooks_persisted", extra={"market_id": market.id, "count": 2})
        payload = CurrentMarketOrderbookResponse(
            market_id=market.id,
            event_slug=market.event_slug,
            up=up_snapshot,
            down=down_snapshot,
        ).model_dump(mode="json")
        await publish_dashboard_event(
            "orderbook_update",
            payload,
            freshness_key="orderbook_rest",
        )
        return {"market_id": market.id, "persisted": 2}


async def _current_market(session: AsyncSession) -> Market | None:
    result = await session.execute(
        select(Market)
        .where(Market.active.is_(True), Market.closed.is_(False))
        .order_by(desc(Market.start_ts), desc(Market.id))
        .limit(1)
    )
    return result.scalar_one_or_none()
