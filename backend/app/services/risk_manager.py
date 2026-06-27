from decimal import Decimal

from app.schemas.strategy import RiskResult, StrategyContext, StrategyDecisionDTO


class RiskManager:
    async def validate_for_paper_trade(
        self,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
    ) -> RiskResult:
        reasons: list[str] = []
        if not context.paper_trading_enabled:
            reasons.append("PAPER_TRADING_DISABLED")
        if context.kill_switch_active:
            reasons.append("KILL_SWITCH_ACTIVE")
        if decision.decision == "NO_TRADE":
            reasons.extend(decision.risk_reasons or [decision.reason])
        if decision.market_price is None:
            reasons.append("LIQUIDITY_TOO_LOW")
        if decision.market_price is not None and decision.market_price <= 0:
            reasons.append("LIQUIDITY_TOO_LOW")
        return RiskResult(passed=not reasons, reasons=list(dict.fromkeys(reasons)))

    async def validate_for_real_trade(
        self,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
        *,
        geoblock_blocked: bool | None = None,
        credentials_configured: bool = False,
        daily_loss_usd: Decimal = Decimal("0"),
    ) -> RiskResult:
        reasons: list[str] = []
        if not context.trading_enabled:
            reasons.append("TRADING_DISABLED")
        if context.kill_switch_active:
            reasons.append("KILL_SWITCH_ACTIVE")
        if geoblock_blocked:
            reasons.append("GEOBLOCK_BLOCKED")
        if not credentials_configured:
            reasons.append("CREDENTIALS_MISSING")
        if daily_loss_usd >= context.max_daily_loss_usd:
            reasons.append("DAILY_LOSS_LIMIT_REACHED")
        if decision.decision == "NO_TRADE":
            reasons.extend(decision.risk_reasons or [decision.reason])
        return RiskResult(passed=not reasons, reasons=list(dict.fromkeys(reasons)))

