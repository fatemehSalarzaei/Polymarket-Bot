from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order


class OrderReconciler:
    async def apply_user_update(self, session: AsyncSession, payload: dict[str, Any]) -> Order | None:
        external_order_id = str(payload.get("order_id") or payload.get("id") or payload.get("orderId") or "")
        if not external_order_id:
            return None

        result = await session.execute(select(Order).where(Order.external_order_id == external_order_id))
        order = result.scalar_one_or_none()
        if order is None:
            return None

        status = payload.get("status")
        if status is not None:
            order.status = str(status).upper()
        size_matched = payload.get("size_matched") or payload.get("filled_size") or payload.get("matched_size")
        if size_matched is not None:
            order.size_matched = Decimal(str(size_matched))
        if order.status in {"FILLED", "MATCHED"} and order.filled_at is None:
            order.filled_at = datetime.now(tz=order.updated_at.tzinfo)
        order.raw_response = {**(order.raw_response or {}), "last_user_update": payload}
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order

