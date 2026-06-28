from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder

from app.schemas.errors import ErrorResponse, ErrorSeverity


@dataclass(frozen=True)
class ErrorDefinition:
    title: str
    message: str
    severity: ErrorSeverity = "error"
    source: str = "backend"
    possible_causes: list[str] = field(default_factory=list)
    recovery_actions: list[str] = field(default_factory=list)


ERROR_DEFINITIONS: dict[str, ErrorDefinition] = {
    "CURRENT_MARKET_MISSING": ErrorDefinition(
        title="Current market is not available",
        message="The bot has not discovered the active BTC Up/Down market yet.",
        severity="warning",
        source="market_discovery",
        possible_causes=["Celery market discovery has not run yet", "Gamma API is unavailable"],
        recovery_actions=["Start celery beat and worker", "Call GET /api/markets/current", "Check Gamma API logs"],
    ),
    "UP_ORDERBOOK_MISSING": ErrorDefinition(
        title="UP orderbook is missing",
        message="The strategy cannot evaluate because no UP orderbook snapshot has been recorded.",
        severity="warning",
        source="clob_orderbook",
        possible_causes=["Orderbook polling has not run", "Market WebSocket is disconnected"],
        recovery_actions=["Start Celery orderbook polling", "Check CLOB API connectivity"],
    ),
    "DOWN_ORDERBOOK_MISSING": ErrorDefinition(
        title="DOWN orderbook is missing",
        message="The strategy cannot evaluate because no DOWN orderbook snapshot has been recorded.",
        severity="warning",
        source="clob_orderbook",
        possible_causes=["Orderbook polling has not run", "Market WebSocket is disconnected"],
        recovery_actions=["Start Celery orderbook polling", "Check CLOB API connectivity"],
    ),
    "CURRENT_CHAINLINK_TICK_MISSING": ErrorDefinition(
        title="BTC live price is not available",
        message="The strategy cannot evaluate the market because no current BTC/USD Chainlink tick has been recorded.",
        severity="warning",
        source="rtds_chainlink",
        possible_causes=[
            "realtime_runner is not running",
            "RTDS WebSocket is disconnected",
            "RTDS subscription format is invalid",
            "Redis/dashboard event pipeline is not running",
        ],
        recovery_actions=[
            "Start python -m app.workers.realtime_runner",
            "Verify POLYMARKET_RTDS_WSS",
            "Check backend logs for RTDS reconnect errors",
            "Wait until a btc/usd tick is persisted",
        ],
    ),
    "START_CHAINLINK_TICK_MISSING": ErrorDefinition(
        title="BTC start price is not available",
        message="The strategy needs a BTC/USD tick near market start to calculate direction.",
        severity="warning",
        source="rtds_chainlink",
        possible_causes=["realtime_runner started after the market began", "RTDS ticks were not persisted"],
        recovery_actions=["Keep realtime_runner running before the next cycle starts", "Check Chainlink tick persistence"],
    ),
    "MARKET_DATA_STALE": ErrorDefinition(
        title="Market data is stale",
        message="The latest market orderbook data is older than the configured freshness limit.",
        severity="warning",
        source="clob_orderbook",
        possible_causes=["Market WebSocket disconnected", "Orderbook polling is delayed"],
        recovery_actions=["Check market_ws_status", "Restart realtime_runner or Celery worker"],
    ),
    "CHAINLINK_DATA_STALE": ErrorDefinition(
        title="BTC price data is stale",
        message="The latest BTC/USD Chainlink tick is older than the configured freshness limit.",
        severity="warning",
        source="rtds_chainlink",
        possible_causes=["RTDS WebSocket disconnected", "No recent btc/usd update received"],
        recovery_actions=["Check rtds_status", "Restart realtime_runner"],
    ),
    "STRATEGY_CONTEXT_INCOMPLETE": ErrorDefinition(
        title="Strategy context is incomplete",
        message="The strategy skipped evaluation because required market, orderbook, or BTC data is missing.",
        severity="warning",
        source="strategy",
        possible_causes=["Market discovery or tick ingestion has not completed"],
        recovery_actions=["Review the listed missing inputs", "Wait for fresh orderbook and Chainlink data"],
    ),
    "MARKET_WS_DISCONNECTED": ErrorDefinition(
        title="Market WebSocket is disconnected",
        message="Live UP/DOWN market ticks are not currently streaming from Polymarket.",
        severity="warning",
        source="clob_market_ws",
        recovery_actions=["Start or restart realtime_runner", "Verify POLYMARKET_MARKET_WSS"],
    ),
    "RTDS_WS_DISCONNECTED": ErrorDefinition(
        title="RTDS WebSocket is disconnected",
        message="Realtime worker is not running or RTDS has not produced BTC/USD ticks yet.",
        severity="warning",
        source="rtds_chainlink",
        recovery_actions=["Start python -m app.workers.realtime_runner", "Check RTDS reconnect logs"],
    ),
    "POLYMARKET_CLOB_HTTP_ERROR": ErrorDefinition(
        title="Polymarket CLOB request failed",
        message="The backend could not fetch CLOB market data from Polymarket.",
        severity="error",
        source="polymarket_clob",
        recovery_actions=["Check Polymarket CLOB status", "Retry after a short delay"],
    ),
    "POLYMARKET_GAMMA_HTTP_ERROR": ErrorDefinition(
        title="Polymarket Gamma request failed",
        message="The backend could not fetch market metadata from Polymarket Gamma.",
        severity="error",
        source="polymarket_gamma",
        recovery_actions=["Check Polymarket Gamma status", "Retry market discovery"],
    ),
    "ORDERBOOK_PARSE_ERROR": ErrorDefinition(
        title="Orderbook response could not be parsed",
        message="Polymarket returned an orderbook payload the backend could not normalize.",
        severity="error",
        source="clob_orderbook",
        recovery_actions=["Check backend logs for the payload shape", "Update the orderbook parser"],
    ),
    "VALIDATION_ERROR": ErrorDefinition(
        title="Request validation failed",
        message="The request contains invalid or missing fields.",
        severity="warning",
        source="api",
    ),
    "HTTP_ERROR": ErrorDefinition(
        title="Request failed",
        message="The backend could not complete this request.",
        severity="error",
        source="api",
    ),
    "INTERNAL_SERVER_ERROR": ErrorDefinition(
        title="Unexpected backend error",
        message="An unexpected backend error occurred.",
        severity="error",
        source="backend",
        recovery_actions=["Check backend logs", "Retry after fixing the underlying error"],
    ),
}


class AppError(Exception):
    def __init__(self, code: str, *, technical_detail: str | None = None, status_code: int = 400) -> None:
        self.code = code
        self.technical_detail = technical_detail
        self.status_code = status_code
        super().__init__(technical_detail or code)


def build_error_response(
    code: str,
    *,
    technical_detail: str | None = None,
    request_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> ErrorResponse:
    definition = ERROR_DEFINITIONS.get(code, ERROR_DEFINITIONS["INTERNAL_SERVER_ERROR"])
    payload = {
        "code": code,
        "title": definition.title,
        "message": definition.message,
        "severity": definition.severity,
        "source": definition.source,
        "possible_causes": list(definition.possible_causes),
        "recovery_actions": list(definition.recovery_actions),
        "technical_detail": technical_detail,
        "timestamp": datetime.now(UTC),
        "request_id": request_id or str(uuid4()),
    }
    if overrides:
        payload.update(overrides)
    return ErrorResponse(**payload)


def error_payload(code: str, *, technical_detail: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    return jsonable_encoder(build_error_response(code, technical_detail=technical_detail, request_id=request_id))


def code_from_detail(detail: Any) -> str:
    if isinstance(detail, dict):
        value = detail.get("code")
        if isinstance(value, str):
            return value
    if isinstance(detail, str):
        normalized = detail.strip().upper()
        if normalized in ERROR_DEFINITIONS:
            return normalized
    return "HTTP_ERROR"
