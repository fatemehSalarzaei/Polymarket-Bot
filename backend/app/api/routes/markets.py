from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.models.tick import ChainlinkTick
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
from app.services.polymarket_gamma import PolymarketGammaClient

router = APIRouter()


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
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MarketResponse.model_validate(market)


@router.get("/markets/current/orderbook", response_model=CurrentMarketOrderbookResponse)
async def get_current_market_orderbook(
    gamma_client: PolymarketGammaClient = Depends(get_gamma_client),
    clob_client: PolymarketClobClient = Depends(get_clob_client),
    session: AsyncSession = Depends(get_session),
) -> CurrentMarketOrderbookResponse:
    discovery = MarketDiscoveryService(gamma_client)
    try:
        active_market = await discovery.discover_current_market()
        market = await persist_active_market(session, active_market)
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
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OrderbookParseError as exc:
        await session.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

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
        raise HTTPException(status_code=404, detail="No BTC tick has been recorded")
    return ChainlinkTickResponse.model_validate(tick)
