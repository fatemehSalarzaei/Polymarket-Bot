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
        if decision.decision != "NO_TRADE" and decision.market_price is None:
            reasons.append("LIQUIDITY_TOO_LOW")
        if decision.market_price is not None and decision.market_price <= 0:
            reasons.append("LIQUIDITY_TOO_LOW")
        return RiskResult(passed=not reasons, reasons=list(dict.fromkeys(reasons)))

    async def validate_for_real_trade(
        self,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
        *,
        bot_running: bool = True,
        env_trading_enabled: bool = False,
        real_trading_confirmation_enabled: bool = False,
        real_order_dry_run: bool = True,
        geoblock_blocked: bool | None = None,
        credentials_configured: bool = False,
        credentials_missing_reason: str | None = None,
        daily_loss_usd: Decimal = Decimal("0"),
    ) -> RiskResult:
        reasons: list[str] = []
        if not bot_running:
            reasons.append("BOT_STOPPED")
        if not context.trading_enabled:
            reasons.append("TRADING_DISABLED")
        if not real_order_dry_run and not env_trading_enabled:
            reasons.append("REAL_TRADING_ENV_DISABLED")
        if not real_order_dry_run and not real_trading_confirmation_enabled:
            reasons.append("REAL_TRADING_CONFIRMATION_DISABLED")
        if context.kill_switch_active:
            reasons.append("KILL_SWITCH_ACTIVE")
        if geoblock_blocked:
            reasons.append("GEOBLOCK_BLOCKED")
        if not credentials_configured:
            reasons.append(credentials_missing_reason or "WALLET_API_CREDENTIALS_MISSING")
        if daily_loss_usd >= context.max_daily_loss_usd:
            reasons.append("DAILY_LOSS_LIMIT_REACHED")
        if decision.decision == "NO_TRADE":
            reasons.extend(decision.risk_reasons or [decision.reason])
        return RiskResult(passed=not reasons, reasons=list(dict.fromkeys(reasons)))
