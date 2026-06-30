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
    status: str = "official_missing"

    def __post_init__(self) -> None:
        if self.official and self.status != "official":
            object.__setattr__(self, "status", "official")


class PolymarketResolutionClient:
    def __init__(self, gamma_client: PolymarketGammaClient | None = None) -> None:
        settings = get_settings()
        self._gamma_client = gamma_client or PolymarketGammaClient(str(settings.polymarket_gamma_host))

    async def get_official_resolution(self, market: Market) -> OfficialResolution:
        try:
            payload = await self._gamma_client.get_event_by_slug(market.event_slug)
        except Exception as exc:
            return OfficialResolution(
                False,
                raw_response={"error": type(exc).__name__, "checked_at": datetime.now(UTC).isoformat()},
                reason="OFFICIAL_RESOLUTION_LOOKUP_FAILED",
                status="official_lookup_failed",
            )
        market_payload = _select_market_payload(payload, market)
        if market_payload is None:
            return OfficialResolution(
                False,
                raw_response={
                    "event": _public_resolution_payload(payload),
                    "market": None,
                    "checked_at": datetime.now(UTC).isoformat(),
                },
                reason="MARKET_NOT_FOUND_IN_GAMMA_EVENT",
                status="official_lookup_failed",
            )

        event_closed = _truthy(payload.get("closed") or payload.get("archived"))
        market_closed = _truthy(market_payload.get("closed") or market_payload.get("archived"))
        official_resolved = _officially_resolved(payload) or _officially_resolved(market_payload)
        outcome = _extract_winning_outcome(market_payload) or _extract_winning_outcome(payload)
        raw_response = {
            "event": _public_resolution_payload(payload),
            "market": _public_resolution_payload(market_payload),
            "checked_at": datetime.now(UTC).isoformat(),
        }
        if event_closed and market_closed and official_resolved and outcome in {"UP", "DOWN"}:
            return OfficialResolution(
                True,
                winning_outcome=outcome,
                raw_response=raw_response,
                status="official",
            )
        return OfficialResolution(
            False,
            raw_response=raw_response,
            reason=_missing_reason(
                event_closed=event_closed,
                market_closed=market_closed,
                official_resolved=official_resolved,
                outcome=outcome,
            ),
            status="official_missing",
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
        winners: list[str] = []
        for outcome, price in zip(outcomes, prices, strict=False):
            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue
            normalized = str(outcome).strip().upper()
            if normalized in {"UP", "DOWN"} and numeric_price >= 0.999:
                winners.append(normalized)
        unique_winners = list(dict.fromkeys(winners))
        if len(unique_winners) == 1:
            return unique_winners[0]
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
        "acceptingOrders",
        "automaticallyResolved",
        "closedTime",
        "outcomes",
        "outcomePrices",
        "umaResolutionStatus",
        "umaResolutionStatuses",
        "resolutionStatus",
        "winningOutcome",
        "outcome",
        "resolution",
        "resolvedOutcome",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "resolved", "closed"}
    return bool(value)


def _officially_resolved(payload: dict[str, Any]) -> bool:
    status_values = []
    for key in ("umaResolutionStatus", "resolutionStatus"):
        value = payload.get(key)
        if value is not None:
            status_values.append(value)
    statuses = _coerce_list(payload.get("umaResolutionStatuses"))
    if statuses:
        status_values.extend(statuses)
    if any(str(value).strip().lower() == "resolved" for value in status_values):
        return True
    return bool(payload.get("automaticallyResolved") or payload.get("closedTime"))


def _missing_reason(*, event_closed: bool, market_closed: bool, official_resolved: bool, outcome: str | None) -> str:
    if not event_closed:
        return "EVENT_NOT_CLOSED"
    if not market_closed:
        return "MARKET_NOT_CLOSED"
    if not official_resolved:
        return "OFFICIAL_RESOLUTION_STATUS_MISSING"
    if outcome not in {"UP", "DOWN"}:
        return "OFFICIAL_WINNING_OUTCOME_NOT_AVAILABLE"
    return "OFFICIAL_RESOLUTION_MISSING"
