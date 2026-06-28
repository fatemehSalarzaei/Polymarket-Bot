from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.market import Market
from app.models.order import Order
from app.models.strategy import StrategyDecision
from app.schemas.strategy import StrategyContext, StrategyDecisionDTO


class PaperTradingEngine:
    async def create_order(
        self,
        session: AsyncSession,
        *,
        market: Market,
        persisted_decision: StrategyDecision,
        decision: StrategyDecisionDTO,
        context: StrategyContext,
        user_id: int | None = None,
    ) -> Order | None:
        if decision.decision not in {"BUY_UP", "BUY_DOWN"} or decision.outcome is None:
            return None
        if decision.market_price is None:
            return None

        token_id = market.up_token_id if decision.outcome == "UP" else market.down_token_id
        price = decision.market_price
        size = context.max_order_size_usd / price
        now = utc_now()

        order = Order(
            user_id=user_id,
            market_id=market.id,
            strategy_decision_id=persisted_decision.id,
            mode="paper",
            external_order_id=None,
            token_id=token_id,
            outcome=decision.outcome,
            side="BUY",
            order_type=context.order_type,
            price=price,
            size=size,
            size_matched=size,
            status="FILLED",
            submitted_at=now,
            updated_at=now,
            filled_at=now,
            raw_response={
                "simulated": True,
                "entry_price": str(decision.market_price),
                "max_slippage": str(context.max_slippage),
            },
        )
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order
