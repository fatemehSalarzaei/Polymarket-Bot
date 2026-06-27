from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market
from app.models.tick import OrderbookSnapshot
from app.schemas.orderbook import OrderbookDTO


async def persist_orderbook_snapshot(
    session: AsyncSession,
    *,
    market: Market,
    outcome: str,
    orderbook: OrderbookDTO,
) -> OrderbookSnapshot:
    snapshot = OrderbookSnapshot(
        market_id=market.id,
        token_id=orderbook.token_id,
        outcome=outcome,
        source_timestamp=orderbook.source_timestamp,
        book_hash=orderbook.book_hash,
        best_bid=orderbook.best_bid,
        best_ask=orderbook.best_ask,
        midpoint=orderbook.midpoint,
        spread=orderbook.spread,
        last_trade_price=orderbook.last_trade_price,
        min_order_size=orderbook.min_order_size,
        tick_size=orderbook.tick_size,
        neg_risk=orderbook.neg_risk,
        bids=[_level_to_dict(level) for level in orderbook.bids],
        asks=[_level_to_dict(level) for level in orderbook.asks],
    )
    session.add(snapshot)
    await session.flush()
    await session.refresh(snapshot)
    return snapshot


def _level_to_dict(level: Any) -> dict[str, str]:
    return {
        "price": str(level.price),
        "size": str(level.size),
    }

