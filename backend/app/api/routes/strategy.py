from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.settings import StrategySettingsPatch, StrategySettingsResponse
from app.schemas.strategy import StrategyDecisionResponse
from app.services.settings import get_or_create_strategy_settings, patch_strategy_settings
from app.services.strategy_persistence import get_latest_decision, list_decisions

router = APIRouter()


@router.get("/strategy/settings", response_model=StrategySettingsResponse)
async def get_strategy_settings(session: AsyncSession = Depends(get_session)) -> StrategySettingsResponse:
    settings = await get_or_create_strategy_settings(session)
    return StrategySettingsResponse.model_validate(settings)


@router.patch("/strategy/settings", response_model=StrategySettingsResponse)
async def update_strategy_settings(
    patch: StrategySettingsPatch,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> StrategySettingsResponse:
    settings = await get_or_create_strategy_settings(session)
    updated = await patch_strategy_settings(
        session,
        settings,
        patch,
        actor="dashboard",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return StrategySettingsResponse.model_validate(updated)


@router.get("/strategy/current-decision", response_model=StrategyDecisionResponse)
async def get_current_decision(session: AsyncSession = Depends(get_session)) -> StrategyDecisionResponse:
    decision = await get_latest_decision(session)
    if decision is None:
        raise HTTPException(status_code=404, detail="No strategy decision has been recorded")
    return StrategyDecisionResponse.model_validate(decision)


@router.get("/strategy/decisions", response_model=list[StrategyDecisionResponse])
async def get_decision_history(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[StrategyDecisionResponse]:
    decisions = await list_decisions(session, limit=limit)
    return [StrategyDecisionResponse.model_validate(decision) for decision in decisions]

