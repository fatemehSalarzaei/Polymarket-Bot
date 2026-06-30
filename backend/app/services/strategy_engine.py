from decimal import Decimal
from typing import Any

from app.schemas.strategy import StrategyContext, StrategyDecisionDTO


class StrategyEngine:
    async def evaluate(self, context: StrategyContext) -> StrategyDecisionDTO:
        raw_context = _json_context(context)

        if context.time_remaining_seconds > context.final_window_seconds:
            return _no_trade(context, "NOT_IN_FINAL_WINDOW", raw_context)

        if context.market_data_age_seconds > Decimal(str(context.max_data_age_seconds)):
            return _no_trade(context, "MARKET_DATA_STALE", raw_context)

        if context.kill_switch_active:
            return _no_trade(context, "KILL_SWITCH_ACTIVE", raw_context)

        if context.up_ask is None or context.down_ask is None:
            return _no_trade(context, "ORDERBOOK_DATA_MISSING", raw_context)

        up_value = context.up_ask
        down_value = context.down_ask
        if up_value == down_value:
            return _no_trade(
                context,
                "PRICE_GAP_TOO_SMALL",
                raw_context,
                compared_up_value=up_value,
                compared_down_value=down_value,
                price_gap=Decimal("0"),
                edge=Decimal("0"),
            )

        if up_value > down_value:
            outcome = "UP"
            ask = up_value
            spread = context.up_spread
            gap = up_value - down_value
            reason = "HIGHER_UP_MARKET_PRICE"
        else:
            outcome = "DOWN"
            ask = down_value
            spread = context.down_spread
            gap = down_value - up_value
            reason = "HIGHER_DOWN_MARKET_PRICE"

        if gap < context.min_edge:
            return _no_trade(
                context,
                "PRICE_GAP_TOO_SMALL",
                raw_context,
                compared_up_value=up_value,
                compared_down_value=down_value,
                price_gap=gap,
                edge=gap,
            )

        if spread is None:
            return _no_trade(
                context,
                "ORDERBOOK_DATA_MISSING",
                raw_context,
                outcome=outcome,
                market_price=ask,
                compared_up_value=up_value,
                compared_down_value=down_value,
                price_gap=gap,
                edge=gap,
            )

        if spread > context.max_spread:
            return _no_trade(
                context,
                "SPREAD_TOO_HIGH",
                raw_context,
                outcome=outcome,
                market_price=ask,
                spread=spread,
                compared_up_value=up_value,
                compared_down_value=down_value,
                price_gap=gap,
                edge=gap,
            )

        raw_context = {
            **raw_context,
            "selected_side": outcome,
            "compared_up_value": str(up_value),
            "compared_down_value": str(down_value),
            "price_gap": str(gap),
        }
        return StrategyDecisionDTO(
            decision=f"BUY_{outcome}",
            outcome=outcome,
            time_remaining_seconds=context.time_remaining_seconds,
            btc_start_price=context.btc_start_price,
            current_price=context.btc_current_price,
            delta=_delta(context),
            up_bid=context.up_bid,
            up_ask=context.up_ask,
            down_bid=context.down_bid,
            down_ask=context.down_ask,
            market_price=ask,
            compared_up_value=up_value,
            compared_down_value=down_value,
            price_gap=gap,
            edge=gap,
            spread=spread,
            risk_passed=True,
            risk_reasons=[],
            reason=reason,
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
    reason: str,
    raw_context: dict[str, Any],
    *,
    outcome: str | None = None,
    market_price: Decimal | None = None,
    spread: Decimal | None = None,
    estimated_probability: Decimal | None = None,
    edge: Decimal | None = None,
    compared_up_value: Decimal | None = None,
    compared_down_value: Decimal | None = None,
    price_gap: Decimal | None = None,
) -> StrategyDecisionDTO:
    raw_context = {
        **raw_context,
        "selected_side": outcome,
        "compared_up_value": str(compared_up_value) if compared_up_value is not None else None,
        "compared_down_value": str(compared_down_value) if compared_down_value is not None else None,
        "price_gap": str(price_gap) if price_gap is not None else None,
    }
    return StrategyDecisionDTO(
        decision="NO_TRADE",
        outcome=outcome,
        time_remaining_seconds=context.time_remaining_seconds,
        btc_start_price=context.btc_start_price,
        current_price=context.btc_current_price,
        delta=_delta(context),
        up_bid=context.up_bid,
        up_ask=context.up_ask,
        down_bid=context.down_bid,
        down_ask=context.down_ask,
        estimated_probability=estimated_probability,
        market_price=market_price,
        compared_up_value=compared_up_value,
        compared_down_value=compared_down_value,
        price_gap=price_gap,
        edge=edge,
        spread=spread,
        risk_passed=False,
        risk_reasons=[reason],
        reason=reason,
        raw_context=raw_context,
    )


def _json_context(context: StrategyContext) -> dict[str, Any]:
    return context.model_dump(mode="json")


def _delta(context: StrategyContext) -> Decimal | None:
    if context.btc_current_price is None or context.btc_start_price is None:
        return None
    return context.btc_current_price - context.btc_start_price
