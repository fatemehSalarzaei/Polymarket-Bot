from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.order import OrderResponse
from app.services.strategy_persistence import list_orders

router = APIRouter()


@router.get("/orders", response_model=list[OrderResponse])
async def get_orders(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[OrderResponse]:
    orders = await list_orders(session, limit=limit)
    return [OrderResponse.model_validate(order) for order in orders]

