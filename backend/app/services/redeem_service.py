from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settlement import Settlement
from app.schemas.execution import GeoblockStatus
from app.schemas.redeem import RedeemAttemptResult, RedeemEligibilityResponse, RedeemRecordResponse
from app.services.geoblock import GeoblockClient
from app.services.polymarket_redeem_adapter import PolymarketRedeemAdapter, build_redeem_adapter
from app.services.settings import get_or_create_strategy_settings


REDEEM_STATUSES = {
    "NOT_ELIGIBLE",
    "READY_TO_REDEEM",
    "REDEEM_SUBMITTED",
    "REDEEM_CONFIRMED",
    "REDEEM_FAILED",
    "SKIPPED_DRY_RUN",
    "SKIPPED_PAPER_ONLY",
}


class GeoblockStatusProvider(Protocol):
    async def get_status(self) -> GeoblockStatus: ...


class RedeemService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        adapter: PolymarketRedeemAdapter | None = None,
        geoblock_client: GeoblockStatusProvider | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._adapter = adapter or build_redeem_adapter(self._settings)
        self._geoblock_client = geoblock_client or GeoblockClient()

    async def check_redeem_eligibility(
        self,
        session: AsyncSession,
        market: Market,
        settlement: Settlement | None,
    ) -> RedeemEligibilityResponse:
        winning_outcome = settlement.winning_outcome if settlement is not None else None
        reasons: list[str] = []

        if settlement is None:
            reasons.append("SETTLEMENT_MISSING")
        elif not _has_official_resolution(settlement):
            reasons.append("OFFICIAL_RESOLUTION_MISSING")
        if not market.condition_id:
            reasons.append("CONDITION_ID_MISSING")
        if not winning_outcome:
            reasons.append("WINNING_OUTCOME_MISSING")

        confirmed = await _get_existing_redeem_record(session, market=market, status="REDEEM_CONFIRMED")
        if confirmed is not None:
            reasons.append("REDEEM_ALREADY_CONFIRMED")

        real_orders = await _real_orders_for_market(session, market_id=market.id)
        if not real_orders:
            paper_orders = await _paper_orders_for_market(session, market_id=market.id)
            reasons.append("PAPER_ONLY" if paper_orders else "REAL_ORDER_MISSING")

        winning_orders = [
            order
            for order in real_orders
            if winning_outcome is not None and order.outcome == winning_outcome and order.size_matched > 0
        ]
        matched_size = sum((order.size_matched for order in winning_orders), Decimal("0"))
        if real_orders and not winning_orders:
            reasons.append("WINNING_REAL_ORDER_MISSING")

        strategy_settings = await get_or_create_strategy_settings(session)
        if not (strategy_settings.trading_enabled or self._settings.redeem_enabled):
            reasons.append("REDEEM_DISABLED")
        if strategy_settings.kill_switch_active or self._settings.kill_switch_active:
            reasons.append("KILL_SWITCH_ACTIVE")
        if not _credentials_configured(self._settings):
            reasons.append("CREDENTIALS_MISSING")

        if "CREDENTIALS_MISSING" not in reasons:
            try:
                geoblock_status = await self._geoblock_client.get_status()
            except Exception as exc:
                reasons.append("GEOBLOCK_CHECK_FAILED")
            else:
                if geoblock_status.blocked:
                    reasons.append("GEOBLOCK_BLOCKED")

        status = _status_from_reasons(reasons, self._settings)
        return RedeemEligibilityResponse(
            market_id=market.id,
            condition_id=market.condition_id,
            winning_outcome=winning_outcome,
            eligible=not reasons,
            status=status,
            reasons=reasons,
            real_winning_order_exists=bool(winning_orders),
            matched_winning_size=matched_size if winning_orders else None,
        )

    async def redeem_winning_position(
        self,
        session: AsyncSession,
        market: Market,
        settlement: Settlement,
    ) -> RedeemAttemptResult:
        eligibility = await self.check_redeem_eligibility(session, market, settlement)
        existing = await _get_existing_redeem_record(session, market=market)
        record = existing or RedeemRecord(
            market_id=market.id,
            settlement_id=settlement.id,
            condition_id=market.condition_id,
            winning_outcome=settlement.winning_outcome,
            status="READY_TO_REDEEM",
            mode="real",
            raw_request={},
            raw_response={},
        )

        if existing is None:
            session.add(record)

        if existing is not None and existing.status == "REDEEM_CONFIRMED":
            return _attempt_result_from_record(existing, reasons=["REDEEM_ALREADY_CONFIRMED"])

        record.settlement_id = settlement.id
        record.winning_outcome = settlement.winning_outcome
        record.wallet_address = self._adapter.wallet_address
        record.raw_request = {
            "condition_id": market.condition_id,
            "index_sets": [1, 2],
            "parent_collection_id": self._settings.ctf_parent_collection_id,
            "pusd_contract_address": self._settings.pusd_contract_address,
        }

        if not eligibility.eligible:
            record.status = "SKIPPED_PAPER_ONLY" if "PAPER_ONLY" in eligibility.reasons else "NOT_ELIGIBLE"
            record.error_message = ",".join(eligibility.reasons)
            record.raw_response = {"eligible": False, "reasons": eligibility.reasons}
            await session.flush()
            await session.refresh(record)
            return _attempt_result_from_record(record, reasons=eligibility.reasons)

        if self._settings.redeem_dry_run or self._settings.real_order_dry_run:
            result = await self._adapter.redeem(market.condition_id, [1, 2])
            record.status = "SKIPPED_DRY_RUN"
            record.tx_hash = None
            record.amount_redeemed = None
            record.balance_before = None
            record.balance_after = None
            record.error_message = "REDEEM_DRY_RUN"
            record.raw_response = result.raw_response
            await session.flush()
            await session.refresh(record)
            return _attempt_result_from_record(record, reasons=["REDEEM_DRY_RUN"])

        try:
            balance_before = await self.sync_wallet_balance()
            result = await self._adapter.redeem(market.condition_id, [1, 2])
            balance_after = await self.sync_wallet_balance()
        except NotImplementedError as exc:
            record.status = "REDEEM_FAILED"
            record.error_message = str(exc)
            record.raw_response = {"error": str(exc), "type": "NotImplementedError"}
        except Exception as exc:
            record.status = "REDEEM_FAILED"
            record.error_message = str(exc)
            record.raw_response = {"error": str(exc), "type": exc.__class__.__name__}
        else:
            record.tx_hash = result.tx_hash
            record.amount_redeemed = result.amount_redeemed
            record.balance_before = balance_before
            record.balance_after = balance_after
            record.raw_response = result.raw_response
            record.error_message = result.error_message
            if result.confirmed:
                record.status = "REDEEM_CONFIRMED"
            elif result.submitted:
                record.status = "REDEEM_SUBMITTED"
            else:
                record.status = "REDEEM_FAILED"
                record.error_message = record.error_message or "REDEEM_NOT_SUBMITTED"

        await session.flush()
        await session.refresh(record)
        return _attempt_result_from_record(record)

    async def sync_wallet_balance(self) -> Decimal | None:
        wallet_address = self._adapter.wallet_address
        if not wallet_address:
            return None
        return await self._adapter.get_pusd_balance(wallet_address)


async def list_redeem_records(session: AsyncSession, *, limit: int = 100) -> list[RedeemRecord]:
    result = await session.execute(select(RedeemRecord).order_by(desc(RedeemRecord.created_at)).limit(limit))
    return list(result.scalars().all())


async def get_redeem_record_for_market(session: AsyncSession, *, market_id: int) -> RedeemRecord | None:
    result = await session.execute(
        select(RedeemRecord)
        .where(RedeemRecord.market_id == market_id, RedeemRecord.mode == "real")
        .order_by(desc(RedeemRecord.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_existing_redeem_record(
    session: AsyncSession,
    *,
    market: Market,
    status: str | None = None,
) -> RedeemRecord | None:
    statement = select(RedeemRecord).where(
        RedeemRecord.market_id == market.id,
        RedeemRecord.condition_id == market.condition_id,
        RedeemRecord.mode == "real",
    )
    if status is not None:
        statement = statement.where(RedeemRecord.status == status)
    result = await session.execute(statement.order_by(desc(RedeemRecord.created_at)).limit(1))
    return result.scalar_one_or_none()


async def _real_orders_for_market(session: AsyncSession, *, market_id: int) -> list[Order]:
    result = await session.execute(select(Order).where(Order.market_id == market_id, Order.mode == "real"))
    return list(result.scalars().all())


async def _paper_orders_for_market(session: AsyncSession, *, market_id: int) -> list[Order]:
    result = await session.execute(select(Order).where(Order.market_id == market_id, Order.mode == "paper"))
    return list(result.scalars().all())


def _status_from_reasons(reasons: list[str], settings: Settings) -> str:
    if "REDEEM_ALREADY_CONFIRMED" in reasons:
        return "REDEEM_CONFIRMED"
    if "PAPER_ONLY" in reasons:
        return "SKIPPED_PAPER_ONLY"
    if reasons:
        return "NOT_ELIGIBLE"
    if settings.redeem_dry_run or settings.real_order_dry_run:
        return "SKIPPED_DRY_RUN"
    return "READY_TO_REDEEM"


def _credentials_configured(settings: Settings) -> bool:
    return bool(
        settings.private_key
        and settings.polymarket_api_key
        and settings.polymarket_api_secret
        and settings.polymarket_api_passphrase
        and settings.polymarket_funder_address
    )


def _has_official_resolution(settlement: Settlement) -> bool:
    raw_resolution = settlement.raw_resolution or {}
    return bool(
        raw_resolution.get("official")
        or raw_resolution.get("official_resolution")
        or raw_resolution.get("resolved")
        or raw_resolution.get("resolved_by_polymarket")
    )


def _attempt_result_from_record(record: RedeemRecord, *, reasons: list[str] | None = None) -> RedeemAttemptResult:
    response = RedeemRecordResponse.model_validate(record)
    return RedeemAttemptResult(
        market_id=record.market_id,
        condition_id=record.condition_id,
        winning_outcome=record.winning_outcome,
        status=record.status,
        record=response,
        tx_hash=record.tx_hash,
        amount_redeemed=record.amount_redeemed,
        balance_before=record.balance_before,
        balance_after=record.balance_after,
        error_message=record.error_message,
        reasons=reasons or [],
    )
