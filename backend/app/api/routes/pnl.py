from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.pnl import PnlSummaryResponse
from app.services.pnl import get_pnl_summary

router = APIRouter()


@router.get("/pnl/summary", response_model=PnlSummaryResponse)
async def get_summary(session: AsyncSession = Depends(get_session)) -> PnlSummaryResponse:
    return await get_pnl_summary(session)

