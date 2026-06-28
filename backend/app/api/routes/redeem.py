from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.market import Market
from app.models.settlement import Settlement
from app.schemas.redeem import RedeemAttemptResult, RedeemRecordResponse, RedeemStatusResponse
from app.services.redeem_service import (
    RedeemService,
    get_redeem_record_for_market,
    list_redeem_records,
)

router = APIRouter()


def get_redeem_service() -> RedeemService:
    return RedeemService()


@router.get("/redeems", response_model=list[RedeemRecordResponse])
async def get_redeems(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[RedeemRecordResponse]:
    records = await list_redeem_records(session, limit=limit)
    return [RedeemRecordResponse.model_validate(record) for record in records]


@router.get("/redeems/{market_id}", response_model=RedeemStatusResponse)
async def get_redeem_by_market(
    market_id: int,
    session: AsyncSession = Depends(get_session),
    service: RedeemService = Depends(get_redeem_service),
) -> RedeemStatusResponse:
    market, settlement = await _market_and_settlement(session, market_id)
    record = await get_redeem_record_for_market(session, market_id=market_id)
    if record is not None:
        return _status_from_record(record)
    eligibility = await service.check_redeem_eligibility(session, market, settlement)
    return RedeemStatusResponse(
        market_id=market.id,
        condition_id=market.condition_id,
        winning_outcome=eligibility.winning_outcome,
        status=eligibility.status,
        real_winning_order_exists=eligibility.real_winning_order_exists,
        reasons=eligibility.reasons,
    )


@router.post("/redeems/{market_id}/attempt", response_model=RedeemAttemptResult)
async def attempt_redeem(
    market_id: int,
    session: AsyncSession = Depends(get_session),
    service: RedeemService = Depends(get_redeem_service),
) -> RedeemAttemptResult:
    market, settlement = await _market_and_settlement(session, market_id)
    if settlement is None:
        raise HTTPException(status_code=400, detail="SETTLEMENT_MISSING")
    result = await service.redeem_winning_position(session, market, settlement)
    await session.commit()
    return result


async def _market_and_settlement(session: AsyncSession, market_id: int) -> tuple[Market, Settlement | None]:
    market_result = await session.execute(select(Market).where(Market.id == market_id))
    market = market_result.scalar_one_or_none()
    if market is None:
        raise HTTPException(status_code=404, detail="MARKET_NOT_FOUND")

    settlement_result = await session.execute(
        select(Settlement).where(Settlement.market_id == market_id).order_by(desc(Settlement.resolved_at)).limit(1)
    )
    return market, settlement_result.scalar_one_or_none()


def _status_from_record(record) -> RedeemStatusResponse:
    return RedeemStatusResponse(
        market_id=record.market_id,
        condition_id=record.condition_id,
        winning_outcome=record.winning_outcome,
        status=record.status,
        tx_hash=record.tx_hash,
        amount_redeemed=record.amount_redeemed,
        balance_before=record.balance_before,
        balance_after=record.balance_after,
        error_message=record.error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
        real_winning_order_exists=record.status not in {"NOT_ELIGIBLE", "SKIPPED_PAPER_ONLY"},
        reasons=[record.error_message] if record.error_message else [],
    )
