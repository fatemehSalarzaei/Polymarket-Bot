from decimal import Decimal
from typing import Any

from app.schemas.strategy import StrategyContext, StrategyDecisionDTO


class StrategyEngine:
    async def evaluate(self, context: StrategyContext) -> StrategyDecisionDTO:
        delta = context.btc_current_price - context.btc_start_price
        raw_context = _json_context(context)

        if context.time_remaining_seconds > context.final_window_seconds:
            return _no_trade(context, delta, "NOT_IN_FINAL_WINDOW", raw_context)

        if context.market_data_age_seconds > Decimal(str(context.max_data_age_seconds)):
            return _no_trade(context, delta, "MARKET_DATA_STALE", raw_context)

        if context.chainlink_data_age_seconds > Decimal(str(context.max_data_age_seconds)):
            return _no_trade(context, delta, "CHAINLINK_DATA_STALE", raw_context)

        if delta == 0:
            return _no_trade(context, delta, "UNKNOWN_DIRECTION", raw_context)

        outcome = "UP" if delta > 0 else "DOWN"
        ask = context.up_ask if outcome == "UP" else context.down_ask
        spread = context.up_spread if outcome == "UP" else context.down_spread

        if ask is None or ask <= 0:
            return _no_trade(context, delta, "LIQUIDITY_TOO_LOW", raw_context, outcome=outcome)

        if spread is None:
            return _no_trade(context, delta, "LIQUIDITY_TOO_LOW", raw_context, outcome=outcome, market_price=ask)

        if spread > context.max_spread:
            return _no_trade(
                context,
                delta,
                "SPREAD_TOO_HIGH",
                raw_context,
                outcome=outcome,
                market_price=ask,
                spread=spread,
            )

        estimated_probability = estimate_probability(context.btc_start_price, delta)
        edge = estimated_probability - ask

        if edge < context.min_edge:
            return _no_trade(
                context,
                delta,
                "EDGE_TOO_LOW",
                raw_context,
                outcome=outcome,
                market_price=ask,
                spread=spread,
                estimated_probability=estimated_probability,
                edge=edge,
            )

        return StrategyDecisionDTO(
            decision=f"BUY_{outcome}",
            outcome=outcome,
            time_remaining_seconds=context.time_remaining_seconds,
            btc_start_price=context.btc_start_price,
            current_price=context.btc_current_price,
            delta=delta,
            up_bid=context.up_bid,
            up_ask=context.up_ask,
            down_bid=context.down_bid,
            down_ask=context.down_ask,
            estimated_probability=estimated_probability,
            market_price=ask,
            edge=edge,
            spread=spread,
            risk_passed=True,
            risk_reasons=[],
            reason="EDGE_PASSED",
            raw_context=raw_context,
        )


def estimate_probability(start_price: Decimal, delta: Decimal) -> Decimal:
    if start_price <= 0:
        return Decimal("0.50")
    delta_ratio = abs(delta) / start_price
    directional_boost = min(delta_ratio * Decimal("20"), Decimal("0.15"))
    return Decimal("0.50") + directional_boost


def _no_trade(
    context: StrategyContext,
    delta: Decimal,
    reason: str,
    raw_context: dict[str, Any],
    *,
    outcome: str | None = None,
    market_price: Decimal | None = None,
    spread: Decimal | None = None,
    estimated_probability: Decimal | None = None,
    edge: Decimal | None = None,
) -> StrategyDecisionDTO:
    return StrategyDecisionDTO(
        decision="NO_TRADE",
        outcome=outcome,
        time_remaining_seconds=context.time_remaining_seconds,
        btc_start_price=context.btc_start_price,
        current_price=context.btc_current_price,
        delta=delta,
        up_bid=context.up_bid,
        up_ask=context.up_ask,
        down_bid=context.down_bid,
        down_ask=context.down_ask,
        estimated_probability=estimated_probability,
        market_price=market_price,
        edge=edge,
        spread=spread,
        risk_passed=False,
        risk_reasons=[reason],
        reason=reason,
        raw_context=raw_context,
    )


def _json_context(context: StrategyContext) -> dict[str, Any]:
    return context.model_dump(mode="json")

