from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery_app import celery_app
from app.db.session import get_sessionmaker
from app.schemas.order import OrderResponse
from app.services.dashboard_event_bus import publish_dashboard_event
from app.services.order_reconciler import OrderReconciler


@celery_app.task(name="app.tasks.orders.reconcile_open_real_orders")
def reconcile_open_real_orders_task() -> dict[str, Any]:
    return asyncio.run(reconcile_open_real_orders_job())


async def reconcile_open_real_orders_job(
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    reconciler: OrderReconciler | None = None,
) -> dict[str, Any]:
    maker = sessionmaker or get_sessionmaker()
    service = reconciler or OrderReconciler()
    async with maker() as session:
        orders = await service.reconcile_open_real_orders(session)
        await session.commit()
        payloads = [OrderResponse.model_validate(order).model_dump(mode="json") for order in orders]
        for payload in payloads:
            await publish_dashboard_event("order_update", payload)
        return {"reconciled": len(payloads), "orders": payloads}
