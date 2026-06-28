from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.models.user import User
from app.schemas.settings import StrategySettingsPatch, StrategySettingsResponse
from app.schemas.strategy import StrategyDecisionResponse
from app.services.settings import get_or_create_strategy_settings, patch_strategy_settings
from app.services.auth import get_current_user, user_id_or_none
from app.services.strategy_persistence import get_latest_decision, list_decisions

router = APIRouter()


@router.get("/strategy/settings", response_model=StrategySettingsResponse)
async def get_strategy_settings(
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> StrategySettingsResponse:
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    return StrategySettingsResponse.model_validate(settings)


@router.patch("/strategy/settings", response_model=StrategySettingsResponse)
async def update_strategy_settings(
    patch: StrategySettingsPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> StrategySettingsResponse:
    settings = await get_or_create_strategy_settings(session, user_id=user_id_or_none(current_user))
    updated = await patch_strategy_settings(
        session,
        settings,
        patch,
        actor=current_user.username if current_user is not None else "dashboard",
        actor_user_id=current_user.id if current_user is not None else None,
        actor_role=current_user.role if current_user is not None else None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return StrategySettingsResponse.model_validate(updated)


@router.get("/strategy/current-decision", response_model=StrategyDecisionResponse)
async def get_current_decision(
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> StrategyDecisionResponse:
    decision = await get_latest_decision(session, user_id=user_id_or_none(current_user))
    if decision is None:
        raise AppError("STRATEGY_CONTEXT_INCOMPLETE", technical_detail="No strategy decision has been recorded", status_code=404)
    return StrategyDecisionResponse.model_validate(decision)


@router.get("/strategy/decisions", response_model=list[StrategyDecisionResponse])
async def get_decision_history(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    current_user: User | None = Depends(get_current_user),
) -> list[StrategyDecisionResponse]:
    decisions = await list_decisions(session, limit=limit, user_id=user_id_or_none(current_user))
    return [StrategyDecisionResponse.model_validate(decision) for decision in decisions]
