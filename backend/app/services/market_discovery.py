from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import Market
from app.schemas.market import ActiveMarketDTO


class MarketDiscoveryError(RuntimeError):
    pass


class MarketNotActiveError(MarketDiscoveryError):
    pass


class TokenMappingError(MarketDiscoveryError):
    pass


class MarketDiscoveryService:
    def __init__(self, gamma_client: Any) -> None:
        self._gamma_client = gamma_client

    @staticmethod
    def compute_cycle_start(now: datetime) -> int:
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        unix_ts = int(now.timestamp())
        return (unix_ts // 900) * 900

    @staticmethod
    def build_btc_15m_slug(start_ts: int) -> str:
        return f"btc-updown-15m-{start_ts}"

    async def discover_current_market(self, now: datetime | None = None) -> ActiveMarketDTO:
        current_time = now or datetime.now(UTC)
        start_ts = self.compute_cycle_start(current_time)
        slug = self.build_btc_15m_slug(start_ts)
        event = await self._gamma_client.get_event_by_slug(slug)
        return self.parse_event(event, expected_slug=slug, start_ts=start_ts)

    @classmethod
    def parse_event(
        cls,
        event: dict[str, Any],
        *,
        expected_slug: str | None = None,
        start_ts: int | None = None,
    ) -> ActiveMarketDTO:
        if not event:
            raise MarketDiscoveryError("Event response is empty")

        event_active = bool(event.get("active", True))
        event_closed = bool(event.get("closed", False))
        if not event_active or event_closed:
            raise MarketNotActiveError("Event is inactive or closed")

        markets = event.get("markets")
        if not isinstance(markets, list) or not markets:
            raise MarketDiscoveryError("Event does not include markets")

        market = cls._select_market(markets)
        market_active = bool(market.get("active", True))
        market_closed = bool(market.get("closed", False))
        if not market_active or market_closed:
            raise MarketNotActiveError("Market is inactive or closed")

        token_map = cls.map_outcome_tokens(market)
        condition_id = str(market.get("conditionId") or market.get("condition_id") or "")
        if not condition_id:
            raise MarketDiscoveryError("Market is missing condition id")

        return ActiveMarketDTO(
            event_slug=str(event.get("slug") or expected_slug or ""),
            market_slug=market.get("slug"),
            condition_id=condition_id,
            question=market.get("question") or event.get("title"),
            active=event_active and market_active,
            closed=event_closed or market_closed,
            start_ts=start_ts,
            end_ts=_maybe_int(event.get("endDateTimestamp") or market.get("endDateTimestamp")),
            up_token_id=token_map["UP"],
            down_token_id=token_map["DOWN"],
            raw_event=event,
            raw_market=market,
        )

    @staticmethod
    def map_outcome_tokens(market: dict[str, Any]) -> dict[str, str]:
        outcomes = _coerce_list(market.get("outcomes"))
        token_ids = _coerce_list(market.get("clobTokenIds"))
        if outcomes is None or token_ids is None:
            raise TokenMappingError("Market must include outcome and clobTokenIds arrays")
        if len(outcomes) != len(token_ids):
            raise TokenMappingError("Outcome and token arrays have different lengths")

        mapped: dict[str, str] = {}
        for outcome, token_id in zip(outcomes, token_ids, strict=True):
            name = str(outcome).strip().upper()
            if name not in {"UP", "DOWN"}:
                continue
            if name in mapped:
                raise TokenMappingError(f"Duplicate {name} outcome")
            mapped[name] = str(token_id)

        if set(mapped) != {"UP", "DOWN"}:
            raise TokenMappingError("Could not unambiguously map UP and DOWN tokens")
        return mapped

    @staticmethod
    def _select_market(markets: list[dict[str, Any]]) -> dict[str, Any]:
        if not all(isinstance(market, dict) for market in markets):
            raise MarketDiscoveryError("Event markets must be objects")
        if len(markets) == 1:
            return markets[0]

        btc_markets = [market for market in markets if "BTC" in str(market.get("question", "")).upper()]
        if len(btc_markets) == 1:
            return btc_markets[0]
        raise MarketDiscoveryError("Could not select a unique BTC market")


async def persist_active_market(session: AsyncSession, dto: ActiveMarketDTO) -> Market:
    result = await session.execute(select(Market).where(Market.event_slug == dto.event_slug))
    market = result.scalar_one_or_none()

    values = dto.model_dump()
    if market is None:
        market = Market(**values)
        session.add(market)
    else:
        for field, value in values.items():
            setattr(market, field, value)

    await session.commit()
    await session.refresh(market)
    return market


def _coerce_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

