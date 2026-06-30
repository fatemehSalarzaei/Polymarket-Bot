from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settlement import Settlement
from app.schemas.execution import GeoblockStatus
from app.schemas.redeem import RedeemAttemptResult, RedeemEligibilityResponse, RedeemRecordResponse
from app.services.geoblock import GeoblockClient
from app.services.order_lifecycle import is_real_order_reconciled_with_match
from app.services.polymarket_redeem_adapter import PolymarketRedeemAdapter, build_redeem_adapter_from_stored_wallet
from app.services.runtime_gate import is_bot_running
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
        self._adapter = adapter
        self._geoblock_client = geoblock_client or GeoblockClient()

    async def check_redeem_eligibility(
        self,
        session: AsyncSession,
        market: Market,
        settlement: Settlement | None,
        user_id: int | None = None,
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
        if not await is_bot_running(session):
            reasons.append("BOT_STOPPED")

        confirmed = await _get_existing_redeem_record(session, market=market, status="REDEEM_CONFIRMED", user_id=user_id)
        if confirmed is not None:
            reasons.append("REDEEM_ALREADY_CONFIRMED")

        real_orders = await _real_orders_for_market(session, market_id=market.id, user_id=user_id)
        if not real_orders:
            paper_orders = await _paper_orders_for_market(session, market_id=market.id, user_id=user_id)
            reasons.append("PAPER_ONLY" if paper_orders else "REAL_ORDER_MISSING")

        winning_orders = [
            order
            for order in real_orders
            if winning_outcome is not None and order.outcome == winning_outcome and is_real_order_reconciled_with_match(order)
        ]
        matched_size = sum((order.size_matched for order in winning_orders), Decimal("0"))
        if real_orders and not winning_orders:
            reasons.append("WINNING_REAL_ORDER_MISSING")
            reasons.append("RECONCILED_WINNING_REAL_ORDER_MISSING")

        strategy_settings = await get_or_create_strategy_settings(session, user_id=user_id)
        if not (strategy_settings.trading_enabled or self._settings.redeem_enabled):
            reasons.append("REDEEM_DISABLED")
        if strategy_settings.kill_switch_active or self._settings.kill_switch_active:
            reasons.append("KILL_SWITCH_ACTIVE")
        if not self._settings.polygon_rpc_url and not (self._settings.redeem_dry_run or self._settings.real_order_dry_run):
            reasons.append("POLYGON_RPC_URL_MISSING")
        if not self._settings.resolved_collateral_token_address and not (self._settings.redeem_dry_run or self._settings.real_order_dry_run):
            reasons.append("COLLATERAL_TOKEN_MISSING")
        if not self._settings.conditional_tokens_contract_address and not (self._settings.redeem_dry_run or self._settings.real_order_dry_run):
            reasons.append("CONDITIONAL_TOKENS_CONTRACT_MISSING")
        if not await self._credentials_configured(session, user_id=user_id):
            reasons.append("CREDENTIALS_MISSING")

        if "CREDENTIALS_MISSING" not in reasons:
            adapter = await self._adapter_for_user(session, user_id=user_id)
            redeem_flow_supported = getattr(adapter, "redeem_flow_supported", True)
            redeem_flow_blocking_reason = getattr(adapter, "redeem_flow_blocking_reason", None)
            if (
                not (self._settings.redeem_dry_run or self._settings.real_order_dry_run)
                and not redeem_flow_supported
                and redeem_flow_blocking_reason
            ):
                reasons.append(redeem_flow_blocking_reason)
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
        user_id: int | None = None,
    ) -> RedeemAttemptResult:
        eligibility = await self.check_redeem_eligibility(session, market, settlement, user_id=user_id)
        existing = await _get_existing_redeem_record(session, market=market, user_id=user_id)
        record = existing or RedeemRecord(
            user_id=user_id,
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
        record.raw_request = {
            "condition_id": market.condition_id,
            "index_sets": [1, 2],
            "parent_collection_id": self._settings.ctf_parent_collection_id,
            "collateral_token_address": self._settings.resolved_collateral_token_address,
        }

        if not eligibility.eligible:
            record.status = "SKIPPED_PAPER_ONLY" if "PAPER_ONLY" in eligibility.reasons else "NOT_ELIGIBLE"
            record.error_message = ",".join(eligibility.reasons)
            record.raw_response = {"eligible": False, "reasons": eligibility.reasons}
            await session.flush()
            await session.refresh(record)
            return _attempt_result_from_record(record, reasons=eligibility.reasons)

        adapter = await self._adapter_for_user(session, user_id=user_id)
        record.wallet_credential_id = adapter.wallet_credential_id
        record.wallet_address = adapter.wallet_address

        if self._settings.redeem_dry_run or self._settings.real_order_dry_run:
            result = await adapter.redeem(market.condition_id, [1, 2])
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
            balance_before = await self.sync_wallet_balance(adapter=adapter)
            result = await adapter.redeem(market.condition_id, [1, 2])
            balance_after = await self.sync_wallet_balance(adapter=adapter)
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
            record.balance_before = balance_before
            record.balance_after = balance_after
            record.amount_redeemed = _amount_redeemed_from_result(result, balance_before, balance_after)
            record.raw_response = dict(result.raw_response)
            record.raw_response["collateral_token_address"] = self._settings.resolved_collateral_token_address
            record.raw_response["balance_before"] = str(balance_before) if balance_before is not None else None
            record.raw_response["balance_after"] = str(balance_after) if balance_after is not None else None
            record.error_message = result.error_message
            if result.amount_redeemed is None and record.amount_redeemed is None:
                record.raw_response["amount_redeemed_unavailable"] = True
                if result.confirmed or result.submitted:
                    record.raw_response["amount_redeemed_unavailable_reason"] = _amount_redeemed_unavailable_reason(
                        balance_before,
                        balance_after,
                    )
            if result.confirmed:
                record.status = "REDEEM_CONFIRMED"
            elif result.submitted and not result.error_message:
                record.status = "REDEEM_SUBMITTED"
            else:
                record.status = "REDEEM_FAILED"
                record.error_message = record.error_message or "REDEEM_NOT_SUBMITTED"

        await session.flush()
        await session.refresh(record)
        return _attempt_result_from_record(record)

    async def sync_wallet_balance(self, *, adapter: PolymarketRedeemAdapter | None = None) -> Decimal | None:
        selected_adapter = adapter or self._adapter
        if selected_adapter is None:
            return None
        wallet_address = selected_adapter.wallet_address
        if not wallet_address:
            return None
        return await selected_adapter.get_pusd_balance(wallet_address)

    async def _adapter_for_user(self, session: AsyncSession, *, user_id: int | None) -> PolymarketRedeemAdapter:
        if self._adapter is not None:
            return self._adapter
        return await build_redeem_adapter_from_stored_wallet(session, user_id=user_id, settings=self._settings)

    async def _credentials_configured(self, session: AsyncSession, *, user_id: int | None) -> bool:
        if self._adapter is not None:
            return self._adapter.credentials_configured
        return await _credentials_configured(session, user_id=user_id)


async def list_redeem_records(session: AsyncSession, *, limit: int = 100, user_id: int | None = None) -> list[RedeemRecord]:
    statement = select(RedeemRecord).options(selectinload(RedeemRecord.settlement))
    if user_id is not None:
        statement = statement.where(RedeemRecord.user_id == user_id)
    result = await session.execute(statement.order_by(desc(RedeemRecord.created_at)).limit(limit))
    return list(result.scalars().all())


async def get_redeem_record_for_market(session: AsyncSession, *, market_id: int, user_id: int | None = None) -> RedeemRecord | None:
    statement = (
        select(RedeemRecord)
        .options(selectinload(RedeemRecord.settlement))
        .where(RedeemRecord.market_id == market_id, RedeemRecord.mode == "real")
    )
    if user_id is not None:
        statement = statement.where(RedeemRecord.user_id == user_id)
    result = await session.execute(
        statement.order_by(desc(RedeemRecord.created_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_existing_redeem_record(
    session: AsyncSession,
    *,
    market: Market,
    status: str | None = None,
    user_id: int | None = None,
) -> RedeemRecord | None:
    statement = select(RedeemRecord).where(
        RedeemRecord.market_id == market.id,
        RedeemRecord.condition_id == market.condition_id,
        RedeemRecord.mode == "real",
    )
    if user_id is not None:
        statement = statement.where(RedeemRecord.user_id == user_id)
    if status is not None:
        statement = statement.where(RedeemRecord.status == status)
    result = await session.execute(statement.order_by(desc(RedeemRecord.created_at)).limit(1))
    return result.scalar_one_or_none()


async def _real_orders_for_market(session: AsyncSession, *, market_id: int, user_id: int | None = None) -> list[Order]:
    statement = select(Order).where(Order.market_id == market_id, Order.mode == "real")
    if user_id is not None:
        statement = statement.where(Order.user_id == user_id)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def _paper_orders_for_market(session: AsyncSession, *, market_id: int, user_id: int | None = None) -> list[Order]:
    statement = select(Order).where(Order.market_id == market_id, Order.mode == "paper")
    if user_id is not None:
        statement = statement.where(Order.user_id == user_id)
    result = await session.execute(statement)
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


async def _credentials_configured(session: AsyncSession, *, user_id: int | None) -> bool:
    try:
        await build_redeem_adapter_from_stored_wallet(session, user_id=user_id)
    except AppError:
        return False
    return True


def _has_official_resolution(settlement: Settlement) -> bool:
    if getattr(settlement, "official_resolution_status", None) == "official":
        return True
    raw_resolution = settlement.raw_resolution or {}
    return bool(
        raw_resolution.get("official")
        or raw_resolution.get("resolved")
        or raw_resolution.get("resolved_by_polymarket")
    )


def _amount_redeemed_from_result(
    result,
    balance_before: Decimal | None,
    balance_after: Decimal | None,
) -> Decimal | None:
    if result.amount_redeemed is not None:
        return result.amount_redeemed
    if result.error_message or not (result.confirmed or result.submitted):
        return None
    if balance_before is None or balance_after is None:
        return None
    delta = balance_after - balance_before
    return delta if delta >= 0 else None


def _amount_redeemed_unavailable_reason(balance_before: Decimal | None, balance_after: Decimal | None) -> str:
    if balance_before is None:
        return "BALANCE_BEFORE_UNAVAILABLE"
    if balance_after is None:
        return "BALANCE_AFTER_UNAVAILABLE"
    return "AMOUNT_REDEEMED_UNAVAILABLE"


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
