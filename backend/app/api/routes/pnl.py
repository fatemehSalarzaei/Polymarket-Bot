from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.schemas.pnl import PnlSummaryResponse
from app.services.auth import get_current_user, user_id_or_none
from app.services.pnl import get_pnl_summary

router = APIRouter()


@router.get("/pnl/summary", response_model=PnlSummaryResponse)
async def get_summary(
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> PnlSummaryResponse:
    return await get_pnl_summary(session, user_id=user_id_or_none(current_user))
