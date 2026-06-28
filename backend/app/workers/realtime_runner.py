from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.schemas.market import MarketResponse
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.tick import ChainlinkTick
from app.services.dashboard_broadcaster import dashboard_broadcaster
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.market_discovery import MarketDiscoveryService, persist_active_market
from app.services.market_ws import MarketWebSocketService
from app.services.polymarket_gamma import PolymarketGammaClient
from app.services.rtds_ws import RTDSWebSocketService


logger = logging.getLogger(__name__)


async def persist_chainlink_tick(tick) -> None:
    async with get_sessionmaker()() as session:
        row = ChainlinkTick(
            symbol=tick.symbol,
            value=tick.value,
            source=tick.source,
            source_timestamp=tick.source_timestamp,
            received_at=tick.received_at,
            raw_payload=tick.raw_payload,
        )
        session.add(row)
        await session.commit()


async def run_realtime_services() -> None:
    settings = get_settings()
    rtds_ws = RTDSWebSocketService(
        url=settings.polymarket_rtds_wss,
        broadcaster=dashboard_broadcaster,
        on_tick=persist_chainlink_tick,
    )
    rtds_task = asyncio.create_task(rtds_ws.run())
    market_task: asyncio.Task | None = None
    subscribed_slug: str | None = None
    service = MarketDiscoveryService(PolymarketGammaClient(str(settings.polymarket_gamma_host)))
    logger.info("realtime_runner_started")

    try:
        while True:
            async with get_sessionmaker()() as session:
                market_dto = await service.discover_current_market(datetime.now(UTC))
                market = await persist_active_market(session, market_dto)
                market_payload = MarketResponse.model_validate(market).model_dump(mode="json")

            if market.event_slug != subscribed_slug:
                if market_task is not None:
                    market_task.cancel()
                    try:
                        await market_task
                    except asyncio.CancelledError:
                        pass

                await dashboard_broadcaster.broadcast("current_market", market_payload, freshness_key="market_discovery")
                await publish_dashboard_event("current_market", market_payload, freshness_key="market_discovery")
                market_ws = MarketWebSocketService(url=settings.polymarket_market_wss, broadcaster=dashboard_broadcaster)
                market_task = asyncio.create_task(market_ws.run(asset_ids=[market.up_token_id, market.down_token_id]))
                subscribed_slug = market.event_slug
                logger.info("market_ws_resubscribed", extra={"market_id": market.id, "event_slug": market.event_slug})

            await asyncio.sleep(30)
    finally:
        if market_task is not None:
            market_task.cancel()
        rtds_task.cancel()
        tasks = [task for task in (market_task, rtds_task) if task is not None]
        await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    asyncio.run(run_realtime_services())


if __name__ == "__main__":
    main()
