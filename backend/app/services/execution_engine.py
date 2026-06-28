from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.market import Market
from app.models.order import Order
from app.models.strategy import StrategyDecision
from app.schemas.execution import GeoblockStatus, PlaceOrderRequest, RealOrderResult
from app.schemas.strategy import StrategyContext, StrategyDecisionDTO
from app.services.polymarket_sdk import BackendOnlyClobSdkWrapper
from app.services.risk_manager import RiskManager


class ExecutionEngine:
    def __init__(
        self,
        *,
        sdk: BackendOnlyClobSdkWrapper,
        risk_manager: RiskManager | None = None,
        dry_run: bool = True,
    ) -> None:
        self._sdk = sdk
        self._risk_manager = risk_manager or RiskManager()
        self._dry_run = dry_run

    async def submit_real_order(
        self,
        session: AsyncSession,
        *,
        market: Market,
        persisted_decision: StrategyDecision,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
        geoblock_status: GeoblockStatus,
        daily_loss_usd: Decimal = Decimal("0"),
    ) -> RealOrderResult:
        risk = await self._risk_manager.validate_for_real_trade(
            decision,
            context,
            geoblock_blocked=geoblock_status.blocked,
            credentials_configured=self._sdk.credentials_configured,
            credentials_missing_reason=self._sdk.credentials_missing_reason,
            daily_loss_usd=daily_loss_usd,
        )
        if not risk.passed:
            order = await self._persist_real_order(
                session,
                market=market,
                persisted_decision=persisted_decision,
                decision=decision,
                context=context,
                status="BLOCKED",
                raw_response={"risk_reasons": risk.reasons, "geoblock": geoblock_status.model_dump(mode="json")},
                error_message=",".join(risk.reasons),
            )
            await session.commit()
            return RealOrderResult(
                submitted=False,
                dry_run=self._dry_run,
                status="BLOCKED",
                order_id=order.id,
                reasons=risk.reasons,
                raw_response=order.raw_response,
            )

        request = self._build_request(market=market, decision=decision, context=context)
        if self._dry_run:
            order = await self._persist_real_order(
                session,
                market=market,
                persisted_decision=persisted_decision,
                decision=decision,
                context=context,
                status="DRY_RUN",
                raw_response={"dry_run": True, "request": request.model_dump(mode="json")},
            )
            await session.commit()
            return RealOrderResult(
                submitted=False,
                dry_run=True,
                status="DRY_RUN",
                order_id=order.id,
                reasons=["DRY_RUN"],
                raw_response=order.raw_response,
            )

        result = await self._sdk.place_order(request)
        order = await self._persist_real_order(
            session,
            market=market,
            persisted_decision=persisted_decision,
            decision=decision,
            context=context,
            status=result.status,
            external_order_id=result.external_order_id,
            raw_response=result.raw_response,
            error_message=result.error_message,
        )
        await session.commit()
        return RealOrderResult(
            submitted=result.submitted,
            dry_run=False,
            status=result.status,
            order_id=order.id,
            external_order_id=result.external_order_id,
            reasons=[] if result.submitted else [result.error_message or "SUBMIT_FAILED"],
            raw_response=result.raw_response,
        )

    def _build_request(
        self,
        *,
        market: Market,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
    ) -> PlaceOrderRequest:
        if decision.outcome is None or decision.market_price is None:
            raise ValueError("Decision is not orderable")
        token_id = market.up_token_id if decision.outcome == "UP" else market.down_token_id
        price = min(decision.market_price + context.max_slippage, Decimal("1"))
        size = context.max_order_size_usd / price
        return PlaceOrderRequest(
            token_id=token_id,
            side="BUY",
            price=price,
            size=size,
            order_type=context.order_type,
        )

    async def _persist_real_order(
        self,
        session: AsyncSession,
        *,
        market: Market,
        persisted_decision: StrategyDecision,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
        status: str,
        external_order_id: str | None = None,
        raw_response: dict | None = None,
        error_message: str | None = None,
    ) -> Order:
        outcome = decision.outcome or "UNKNOWN"
        token_id = market.up_token_id if outcome == "UP" else market.down_token_id if outcome == "DOWN" else ""
        price = min((decision.market_price or Decimal("0")) + context.max_slippage, Decimal("1"))
        size = context.max_order_size_usd / price if price > 0 else Decimal("0")
        now = utc_now()
        order = Order(
            market_id=market.id,
            strategy_decision_id=persisted_decision.id,
            mode="real",
            external_order_id=external_order_id,
            token_id=token_id,
            outcome=outcome,
            side="BUY",
            order_type=context.order_type,
            price=price,
            size=size,
            size_matched=Decimal("0"),
            status=status,
            submitted_at=now,
            updated_at=now,
            raw_response=raw_response or {},
            error_message=error_message,
        )
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order
