from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.models.market import Market
from app.services.polymarket_gamma import PolymarketGammaClient


@dataclass(frozen=True)
class OfficialResolution:
    official: bool
    winning_outcome: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None


class PolymarketResolutionClient:
    def __init__(self, gamma_client: PolymarketGammaClient | None = None) -> None:
        settings = get_settings()
        self._gamma_client = gamma_client or PolymarketGammaClient(str(settings.polymarket_gamma_host))

    async def get_official_resolution(self, market: Market) -> OfficialResolution:
        payload = await self._gamma_client.get_event_by_slug(market.event_slug)
        market_payload = _select_market_payload(payload, market)
        if market_payload is None:
            return OfficialResolution(False, raw_response=payload, reason="MARKET_NOT_FOUND_IN_GAMMA_EVENT")

        closed = bool(payload.get("closed") or market_payload.get("closed") or market_payload.get("archived"))
        outcome = _extract_winning_outcome(market_payload) or _extract_winning_outcome(payload)
        if closed and outcome in {"UP", "DOWN"}:
            return OfficialResolution(
                True,
                winning_outcome=outcome,
                raw_response={
                    "event": _public_resolution_payload(payload),
                    "market": _public_resolution_payload(market_payload),
                    "checked_at": datetime.now(UTC).isoformat(),
                },
            )
        return OfficialResolution(
            False,
            raw_response={
                "event": _public_resolution_payload(payload),
                "market": _public_resolution_payload(market_payload),
                "checked_at": datetime.now(UTC).isoformat(),
            },
            reason="OFFICIAL_WINNING_OUTCOME_NOT_AVAILABLE",
        )


def _select_market_payload(event: dict[str, Any], market: Market) -> dict[str, Any] | None:
    markets = event.get("markets")
    if not isinstance(markets, list):
        return None
    for candidate in markets:
        if not isinstance(candidate, dict):
            continue
        condition_id = str(candidate.get("conditionId") or candidate.get("condition_id") or "")
        slug = str(candidate.get("slug") or "")
        if condition_id and condition_id == market.condition_id:
            return candidate
        if slug and slug == market.market_slug:
            return candidate
    return markets[0] if len(markets) == 1 and isinstance(markets[0], dict) else None


def _extract_winning_outcome(payload: dict[str, Any]) -> str | None:
    for key in (
        "winningOutcome",
        "winning_outcome",
        "outcome",
        "resolution",
        "resolvedOutcome",
        "resolved_outcome",
    ):
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip().upper()
            if normalized in {"UP", "DOWN"}:
                return normalized

    outcomes = _coerce_list(payload.get("outcomes"))
    prices = _coerce_list(payload.get("outcomePrices") or payload.get("outcome_prices"))
    if outcomes and prices and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices, strict=False):
            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue
            normalized = str(outcome).strip().upper()
            if normalized in {"UP", "DOWN"} and numeric_price >= 0.999:
                return normalized
    return None


def _coerce_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _public_resolution_payload(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "id",
        "slug",
        "conditionId",
        "condition_id",
        "closed",
        "archived",
        "active",
        "outcomes",
        "outcomePrices",
        "winningOutcome",
        "outcome",
        "resolution",
        "resolvedOutcome",
    }
    return {key: value for key, value in payload.items() if key in allowed}
