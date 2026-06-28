import logging

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.config import get_settings
from app.db.session import get_session
from app.models.tick import ChainlinkTick
from app.models.market import Market
from app.models.tick import OrderbookSnapshot
from app.schemas.market import MarketResponse
from app.schemas.orderbook import CurrentMarketOrderbookResponse
from app.schemas.tick import ChainlinkTickResponse
from app.services.market_discovery import (
    MarketDiscoveryError,
    MarketDiscoveryService,
    persist_active_market,
)
from app.services.orderbook import persist_orderbook_snapshot
from app.services.polymarket_clob import OrderbookParseError, PolymarketClobClient
from app.services.polymarket_errors import PolymarketHttpError
from app.services.polymarket_gamma import PolymarketGammaClient

router = APIRouter()
logger = logging.getLogger(__name__)


def get_gamma_client() -> PolymarketGammaClient:
    settings = get_settings()
    return PolymarketGammaClient(str(settings.polymarket_gamma_host))


def get_clob_client() -> PolymarketClobClient:
    settings = get_settings()
    return PolymarketClobClient(str(settings.polymarket_clob_host))


@router.get("/markets/current", response_model=MarketResponse)
async def get_current_market(
    gamma_client: PolymarketGammaClient = Depends(get_gamma_client),
    session: AsyncSession = Depends(get_session),
) -> MarketResponse:
    service = MarketDiscoveryService(gamma_client)
    try:
        active_market = await service.discover_current_market()
        market = await persist_active_market(session, active_market)
    except MarketDiscoveryError as exc:
        raise AppError("CURRENT_MARKET_MISSING", technical_detail=str(exc), status_code=503) from exc
    return MarketResponse.model_validate(market)


@router.get("/markets/current/orderbook", response_model=CurrentMarketOrderbookResponse)
async def get_current_market_orderbook(
    gamma_client: PolymarketGammaClient = Depends(get_gamma_client),
    clob_client: PolymarketClobClient = Depends(get_clob_client),
    session: AsyncSession = Depends(get_session),
) -> CurrentMarketOrderbookResponse:
    discovery = MarketDiscoveryService(gamma_client)
    market: Market | None = None
    market_id: int | None = None
    event_slug: str | None = None
    try:
        active_market = await discovery.discover_current_market()
        market = await persist_active_market(session, active_market)
        market_id = market.id
        event_slug = market.event_slug
        up_orderbook = await clob_client.get_orderbook(market.up_token_id)
        down_orderbook = await clob_client.get_orderbook(market.down_token_id)
        up_snapshot = await persist_orderbook_snapshot(
            session,
            market=market,
            outcome="UP",
            orderbook=up_orderbook,
        )
        down_snapshot = await persist_orderbook_snapshot(
            session,
            market=market,
            outcome="DOWN",
            orderbook=down_orderbook,
        )
        await session.commit()
    except MarketDiscoveryError as exc:
        await session.rollback()
        market = await _current_market(session)
        if market is None:
            raise AppError("CURRENT_MARKET_MISSING", technical_detail=str(exc), status_code=503) from exc
        cached = await _cached_orderbook_response(session, market_id=market.id, event_slug=market.event_slug)
        if cached is not None:
            logger.warning("cached_orderbook_served_after_market_discovery_error", extra={"market_id": market.id})
            return cached
        raise AppError("CURRENT_MARKET_MISSING", technical_detail=str(exc), status_code=503) from exc
    except PolymarketHttpError as exc:
        await session.rollback()
        if market_id is None or event_slug is None:
            market = await _current_market(session)
            if market is not None:
                market_id = market.id
                event_slug = market.event_slug
        if market_id is not None and event_slug is not None:
            cached = await _cached_orderbook_response(session, market_id=market_id, event_slug=event_slug)
            if cached is not None:
                logger.warning(
                    "cached_orderbook_served_after_polymarket_error",
                    extra={"market_id": market_id, "code": exc.code, "endpoint": exc.endpoint},
                )
                return cached
        raise AppError(exc.code, technical_detail=exc.technical_detail, status_code=503) from exc
    except OrderbookParseError as exc:
        await session.rollback()
        raise AppError("ORDERBOOK_PARSE_ERROR", technical_detail=str(exc), status_code=502) from exc

    return CurrentMarketOrderbookResponse(
        market_id=market.id,
        event_slug=market.event_slug,
        up=up_snapshot,
        down=down_snapshot,
    )


@router.get("/markets/current/btc", response_model=ChainlinkTickResponse)
async def get_current_btc_tick(session: AsyncSession = Depends(get_session)) -> ChainlinkTickResponse:
    result = await session.execute(select(ChainlinkTick).order_by(desc(ChainlinkTick.received_at), desc(ChainlinkTick.id)).limit(1))
    tick = result.scalar_one_or_none()
    if tick is None:
        raise AppError("CURRENT_CHAINLINK_TICK_MISSING", status_code=404)
    return ChainlinkTickResponse.model_validate(tick)


async def _current_market(session: AsyncSession) -> Market | None:
    result = await session.execute(
        select(Market)
        .where(Market.active.is_(True), Market.closed.is_(False))
        .order_by(desc(Market.start_ts), desc(Market.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _cached_orderbook_response(
    session: AsyncSession,
    *,
    market_id: int,
    event_slug: str,
) -> CurrentMarketOrderbookResponse | None:
    up = await _latest_snapshot(session, market_id=market_id, outcome="UP")
    down = await _latest_snapshot(session, market_id=market_id, outcome="DOWN")
    if up is None or down is None:
        return None
    return CurrentMarketOrderbookResponse(
        market_id=market_id,
        event_slug=event_slug,
        up=up,
        down=down,
    )


async def _latest_snapshot(session: AsyncSession, *, market_id: int, outcome: str) -> OrderbookSnapshot | None:
    result = await session.execute(
        select(OrderbookSnapshot)
        .where(OrderbookSnapshot.market_id == market_id, OrderbookSnapshot.outcome == outcome)
        .order_by(desc(OrderbookSnapshot.received_at), desc(OrderbookSnapshot.id))
        .limit(1)
    )
    return result.scalar_one_or_none()
