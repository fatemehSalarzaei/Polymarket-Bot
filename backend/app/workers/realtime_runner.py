from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models.tick import ChainlinkTick
from app.services.dashboard_broadcaster import dashboard_broadcaster
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
    async with get_sessionmaker()() as session:
        market_dto = await MarketDiscoveryService(
            PolymarketGammaClient(str(settings.polymarket_gamma_host))
        ).discover_current_market(datetime.now(UTC))
        market = await persist_active_market(session, market_dto)

    market_ws = MarketWebSocketService(
        url=str(settings.polymarket_clob_host).replace("https://", "wss://").replace("http://", "ws://") + "/ws/market",
        broadcaster=dashboard_broadcaster,
    )
    rtds_ws = RTDSWebSocketService(
        url=settings.polymarket_rtds_wss,
        broadcaster=dashboard_broadcaster,
        on_tick=persist_chainlink_tick,
    )
    logger.info("realtime_runner_started", extra={"market_id": market.id, "event_slug": market.event_slug})
    await asyncio.gather(
        market_ws.run(asset_ids=[market.up_token_id, market.down_token_id]),
        rtds_ws.run(),
    )


def main() -> None:
    asyncio.run(run_realtime_services())


if __name__ == "__main__":
    main()
