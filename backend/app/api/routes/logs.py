from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogResponse

router = APIRouter()


@router.get("/logs", response_model=list[AuditLogResponse])
async def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogResponse]:
    result = await session.execute(select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(limit))
    return [AuditLogResponse.model_validate(row) for row in result.scalars().all()]

