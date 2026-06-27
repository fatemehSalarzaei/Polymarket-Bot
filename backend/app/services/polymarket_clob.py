from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.schemas.orderbook import OrderbookDTO, OrderbookLevel


class OrderbookParseError(ValueError):
    pass


class PolymarketClobClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def get_orderbook(self, token_id: str) -> OrderbookDTO:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=10) as client:
            response = await client.get("/book", params={"token_id": token_id})
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise OrderbookParseError("CLOB orderbook response must be a JSON object")
        return normalize_orderbook(payload, fallback_token_id=token_id)


def normalize_orderbook(payload: dict[str, Any], *, fallback_token_id: str | None = None) -> OrderbookDTO:
    token_id = str(payload.get("asset_id") or payload.get("token_id") or fallback_token_id or "")
    if not token_id:
        raise OrderbookParseError("Orderbook response is missing token id")

    bids = _parse_levels(payload.get("bids"))
    asks = _parse_levels(payload.get("asks"))
    best_bid = max((level.price for level in bids), default=None)
    best_ask = min((level.price for level in asks), default=None)
    midpoint = _midpoint(best_bid, best_ask)
    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None

    return OrderbookDTO(
        market=_maybe_str(payload.get("market")),
        token_id=token_id,
        source_timestamp=_parse_timestamp(payload.get("timestamp")),
        book_hash=_maybe_str(payload.get("hash")),
        bids=bids,
        asks=asks,
        min_order_size=_maybe_decimal(payload.get("min_order_size")),
        tick_size=_maybe_decimal(payload.get("tick_size")),
        neg_risk=_maybe_bool(payload.get("neg_risk")),
        last_trade_price=_maybe_decimal(payload.get("last_trade_price")),
        best_bid=best_bid,
        best_ask=best_ask,
        midpoint=midpoint,
        spread=spread,
        raw_payload=payload,
    )


def _parse_levels(value: Any) -> list[OrderbookLevel]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OrderbookParseError("Orderbook levels must be arrays")

    levels: list[OrderbookLevel] = []
    for item in value:
        if not isinstance(item, dict):
            raise OrderbookParseError("Orderbook level must be an object")
        price = _maybe_decimal(item.get("price"))
        size = _maybe_decimal(item.get("size"))
        if price is None or size is None:
            raise OrderbookParseError("Orderbook level is missing price or size")
        levels.append(OrderbookLevel(price=price, size=size))
    return levels


def _midpoint(best_bid: Decimal | None, best_ask: Decimal | None) -> Decimal | None:
    if best_bid is None or best_ask is None:
        return None
    return (best_bid + best_ask) / Decimal("2")


def _maybe_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise OrderbookParseError(f"Invalid decimal value: {value}") from None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, tz=UTC)
    if isinstance(value, str):
        if value.isdigit():
            return _parse_timestamp(int(value))
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _maybe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _maybe_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

