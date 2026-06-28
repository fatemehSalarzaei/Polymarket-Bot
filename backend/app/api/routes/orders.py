from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.schemas.order import OrderResponse
from app.services.auth import get_current_user, user_id_or_none
from app.services.strategy_persistence import list_orders

router = APIRouter()


@router.get("/orders", response_model=list[OrderResponse])
async def get_orders(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> list[OrderResponse]:
    orders = await list_orders(session, limit=limit, user_id=user_id_or_none(current_user))
    return [OrderResponse.model_validate(order) for order in orders]
