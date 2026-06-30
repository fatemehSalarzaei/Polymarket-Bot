from __future__ import annotations

from decimal import Decimal

from app.models.order import Order


ORDER_STATUS_BLOCKED = "BLOCKED"
ORDER_STATUS_DRY_RUN = "DRY_RUN"
ORDER_STATUS_SUBMITTED = "SUBMITTED"
ORDER_STATUS_RECONCILED = "RECONCILED"
ORDER_STATUS_PARTIALLY_FILLED = "PARTIALLY_FILLED"
ORDER_STATUS_FILLED = "FILLED"
ORDER_STATUS_FAILED = "FAILED"
ORDER_STATUS_CANCELLED = "CANCELLED"
ORDER_STATUS_EXPIRED = "EXPIRED"
ORDER_STATUS_SETTLEMENT_ELIGIBLE = "SETTLEMENT_ELIGIBLE"

TERMINAL_ORDER_STATUSES = {
    ORDER_STATUS_BLOCKED,
    ORDER_STATUS_DRY_RUN,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_FAILED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_SETTLEMENT_ELIGIBLE,
}

RECONCILABLE_ORDER_STATUSES = {
    ORDER_STATUS_SUBMITTED,
    ORDER_STATUS_RECONCILED,
    ORDER_STATUS_PARTIALLY_FILLED,
    "OPEN",
    "LIVE",
    "MATCHED",
}

REAL_SETTLEMENT_ELIGIBLE_STATUSES = {
    ORDER_STATUS_RECONCILED,
    ORDER_STATUS_PARTIALLY_FILLED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_SETTLEMENT_ELIGIBLE,
}


def normalize_order_status(value: object) -> str | None:
    if value is None:
        return None
    status = str(value).upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "LIVE": ORDER_STATUS_SUBMITTED,
        "OPEN": ORDER_STATUS_SUBMITTED,
        "UNMATCHED": ORDER_STATUS_SUBMITTED,
        "PARTIAL": ORDER_STATUS_PARTIALLY_FILLED,
        "PARTIAL_FILL": ORDER_STATUS_PARTIALLY_FILLED,
        "PARTIALLY_MATCHED": ORDER_STATUS_PARTIALLY_FILLED,
        "MATCHED": ORDER_STATUS_FILLED,
        "CANCELED": ORDER_STATUS_CANCELLED,
        "ERROR": ORDER_STATUS_FAILED,
    }
    return aliases.get(status, status)


def lifecycle_status_from_reconciliation(raw_status: object, *, size: Decimal, size_matched: Decimal) -> str:
    status = normalize_order_status(raw_status) or ORDER_STATUS_RECONCILED
    if status == ORDER_STATUS_FILLED:
        return ORDER_STATUS_FILLED if size_matched > 0 else ORDER_STATUS_FAILED
    if status in {ORDER_STATUS_FAILED, ORDER_STATUS_CANCELLED, ORDER_STATUS_EXPIRED}:
        return status
    if size_matched <= 0:
        return ORDER_STATUS_SUBMITTED
    if size > 0 and size_matched >= size:
        return ORDER_STATUS_FILLED
    return ORDER_STATUS_PARTIALLY_FILLED


def is_real_order_reconciled_with_match(order: Order) -> bool:
    return (
        order.mode == "real"
        and order.status in REAL_SETTLEMENT_ELIGIBLE_STATUSES
        and Decimal(order.size_matched or 0) > 0
    )
