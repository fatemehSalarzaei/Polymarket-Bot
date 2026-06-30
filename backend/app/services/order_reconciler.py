from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.models.order import Order
from app.services.order_lifecycle import (
    ORDER_STATUS_FAILED,
    RECONCILABLE_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    lifecycle_status_from_reconciliation,
)
from app.services.polymarket_sdk import build_clob_sdk_from_stored_wallet


class OrderReconciler:
    async def reconcile_open_real_orders(self, session: AsyncSession, *, limit: int = 100) -> list[Order]:
        result = await session.execute(
            select(Order)
            .where(
                Order.mode == "real",
                Order.external_order_id.is_not(None),
                Order.status.not_in(TERMINAL_ORDER_STATUSES),
            )
            .order_by(Order.updated_at.asc())
            .limit(limit)
        )
        orders = list(result.scalars().all())
        reconciled: list[Order] = []
        for order in orders:
            if not order.external_order_id:
                continue
            try:
                sdk = await build_clob_sdk_from_stored_wallet(session, user_id=order.user_id)
                payload = await sdk.get_order(order.external_order_id)
            except Exception as exc:
                payload = {"status": ORDER_STATUS_FAILED, "error": type(exc).__name__}
            updated = await self.apply_user_update_for_order(session, order=order, payload=payload)
            if updated is not None:
                reconciled.append(updated)
        return reconciled

    async def apply_user_update(self, session: AsyncSession, payload: dict[str, Any]) -> Order | None:
        external_order_id = str(payload.get("order_id") or payload.get("id") or payload.get("orderId") or "")
        if not external_order_id:
            return None

        result = await session.execute(select(Order).where(Order.external_order_id == external_order_id))
        order = result.scalar_one_or_none()
        if order is None:
            return None

        return await self._apply_payload(session, order, payload)

    async def apply_user_update_for_order(
        self,
        session: AsyncSession,
        *,
        order: Order,
        payload: dict[str, Any],
    ) -> Order:
        return await self._apply_payload(session, order, payload)

    async def _apply_payload(self, session: AsyncSession, order: Order, payload: dict[str, Any]) -> Order:
        size_matched = (
            payload.get("size_matched")
            or payload.get("filled_size")
            or payload.get("matched_size")
            or payload.get("filledSize")
            or payload.get("sizeMatched")
        )
        if size_matched is not None:
            order.size_matched = Decimal(str(size_matched))
        status = lifecycle_status_from_reconciliation(
            payload.get("status") or payload.get("state"),
            size=Decimal(order.size or 0),
            size_matched=Decimal(order.size_matched or 0),
        )
        order.status = status
        if order.status in {"FILLED", "SETTLEMENT_ELIGIBLE"} and order.filled_at is None:
            order.filled_at = datetime.now(tz=order.updated_at.tzinfo)
        order.updated_at = utc_now()
        order.raw_response = {**(order.raw_response or {}), "last_reconciliation": _safe_order_payload(payload)}
        session.add(order)
        await session.flush()
        await session.refresh(order)
        return order
def _safe_order_payload(payload: dict[str, Any]) -> dict[str, Any]:
    forbidden = {"private_key", "api_secret", "api_passphrase", "secret", "passphrase", "signature"}
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if str(key).lower() in forbidden:
            safe[str(key)] = "[redacted]"
        else:
            safe[str(key)] = value
    return safe
