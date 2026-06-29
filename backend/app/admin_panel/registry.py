from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.inspection import inspect

from app.models.audit import AuditLog
from app.models.market import Market
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settings import StrategySettings
from app.models.settlement import Settlement
from app.models.strategy import StrategyDecision
from app.models.user import User
from app.models.wallet import WalletCredential

FORBIDDEN_FIELDS = {
    "password_hash",
    "encrypted_private_key",
    "encrypted_api_key",
    "encrypted_api_secret",
    "encrypted_api_passphrase",
    "private_key",
    "api_secret",
    "api_passphrase",
    "credential_encryption_key",
    "jwt_secret_key",
}

WALLET_MASKED_FIELDS = [
    "id",
    "user_id",
    "wallet_address",
    "funder_address",
    "signature_type",
    "chain_id",
    "api_key_configured",
    "is_configured",
    "is_active",
    "last_validated_at",
    "last_error",
    "created_at",
    "updated_at",
]

@dataclass(frozen=True)
class AdminTable:
    name: str
    label: str
    model: type[Any]
    creatable: bool = False
    editable: bool = False
    deletable: bool = False
    list_fields: tuple[str, ...] | None = None
    detail_fields: tuple[str, ...] | None = None
    create_fields: tuple[str, ...] | None = None
    edit_fields: tuple[str, ...] | None = None
    row_transform: Callable[[Any, bool], dict[str, Any]] | None = None

    @property
    def read_only(self) -> bool:
        return not self.creatable and not self.editable and not self.deletable

    def list_display_fields(self) -> list[str]:
        if self.list_fields is not None:
            return [field for field in self.list_fields if field not in FORBIDDEN_FIELDS]
        return self.public_fields()

    def detail_display_fields(self) -> list[str]:
        if self.detail_fields is not None:
            return [field for field in self.detail_fields if field not in FORBIDDEN_FIELDS]
        return self.public_fields()

    def public_fields(self) -> list[str]:
        return [
            column.key
            for column in inspect(self.model).columns
            if column.key not in FORBIDDEN_FIELDS
        ]

    def form_fields(self, *, creating: bool) -> list[str]:
        configured = self.create_fields if creating else self.edit_fields
        if configured is None:
            configured = ()
        return [field for field in configured if field not in FORBIDDEN_FIELDS]

    def public_row(self, row: Any, *, detail: bool = False) -> dict[str, Any]:
        if self.row_transform is not None:
            return self.row_transform(row, detail)
        fields = self.detail_display_fields() if detail else self.list_display_fields()
        return {field: getattr(row, field) for field in fields}

    def can_create(self, user: Any) -> bool:
        return self.creatable and getattr(user, "role", None) == "super_user"

    def can_edit(self, user: Any) -> bool:
        return self.editable and getattr(user, "role", None) == "super_user"

    def can_delete(self, user: Any) -> bool:
        return self.deletable and getattr(user, "role", None) == "super_user"


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Enabled" if value else "Disabled"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, (dict, list)):
        return "View details"
    text = str(value)
    return text if len(text) <= 96 else f"{text[:93]}..."


def masked_wallet_row(row: WalletCredential) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "wallet_address": row.wallet_address,
        "funder_address": row.funder_address,
        "signature_type": row.signature_type,
        "chain_id": row.chain_id,
        "api_key_configured": bool(row.encrypted_api_key),
        "is_configured": row.is_configured,
        "is_active": row.is_active,
        "last_validated_at": row.last_validated_at,
        "last_error": row.last_error,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def masked_wallet_list_row(row: WalletCredential) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "wallet_address": _mask_address(row.wallet_address),
        "api_key_configured": bool(row.encrypted_api_key),
        "is_configured": row.is_configured,
        "is_active": row.is_active,
        "last_validated_at": row.last_validated_at,
        "updated_at": row.updated_at,
    }


def _mask_address(value: str | None) -> str | None:
    if not value or len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


TABLES: dict[str, AdminTable] = {
    "users": AdminTable(
        name="users",
        label="Users",
        model=User,
        creatable=True,
        editable=True,
        list_fields=("id", "username", "email", "role", "is_active", "created_at", "last_login_at"),
        create_fields=("username", "email", "password", "role", "is_active"),
        edit_fields=("username", "email", "password", "role", "is_active"),
    ),
    "markets": AdminTable(
        name="markets",
        label="Markets",
        model=Market,
        editable=True,
        list_fields=("id", "event_slug", "question", "active", "closed", "start_ts", "end_ts", "updated_at"),
        edit_fields=("market_slug", "question", "active", "closed", "start_ts", "end_ts"),
    ),
    "strategy_settings": AdminTable(
        name="strategy_settings",
        label="Strategy Settings",
        model=StrategySettings,
        creatable=True,
        editable=True,
        list_fields=(
            "id",
            "user_id",
            "paper_trading_enabled",
            "trading_enabled",
            "kill_switch_active",
            "min_edge",
            "max_order_size_usd",
            "updated_at",
        ),
        create_fields=(
            "user_id",
            "paper_trading_enabled",
            "trading_enabled",
            "kill_switch_active",
            "final_window_seconds",
            "min_edge",
            "max_spread",
            "max_slippage",
            "max_order_size_usd",
            "max_daily_loss_usd",
            "max_data_age_seconds",
            "order_type",
        ),
        edit_fields=(
            "user_id",
            "paper_trading_enabled",
            "trading_enabled",
            "kill_switch_active",
            "final_window_seconds",
            "min_edge",
            "max_spread",
            "max_slippage",
            "max_order_size_usd",
            "max_daily_loss_usd",
            "max_data_age_seconds",
            "order_type",
        ),
    ),
    "strategy_decisions": AdminTable(
        name="strategy_decisions",
        label="Strategy Decisions",
        model=StrategyDecision,
        list_fields=("id", "user_id", "market_id", "decision", "outcome", "mode", "edge", "risk_passed", "created_at"),
    ),
    "orders": AdminTable(
        name="orders",
        label="Orders",
        model=Order,
        list_fields=(
            "id",
            "user_id",
            "market_id",
            "mode",
            "side",
            "outcome",
            "price",
            "size",
            "status",
            "submitted_at",
        ),
    ),
    "settlements": AdminTable(
        name="settlements",
        label="Settlements",
        model=Settlement,
        list_fields=("id", "user_id", "market_id", "winning_outcome", "paper_pnl", "real_pnl", "resolved_at"),
    ),
    "redeem_records": AdminTable(
        name="redeem_records",
        label="Redeem Records",
        model=RedeemRecord,
        editable=True,
        list_fields=("id", "user_id", "market_id", "winning_outcome", "status", "mode", "amount_redeemed", "updated_at"),
        edit_fields=("status", "error_message"),
    ),
    "audit_logs": AdminTable(
        name="audit_logs",
        label="Audit Logs",
        model=AuditLog,
        list_fields=("id", "user_id", "actor", "actor_role", "action", "entity_type", "entity_id", "created_at"),
    ),
    "wallet_credentials_masked": AdminTable(
        name="wallet_credentials_masked",
        label="Wallet Credentials",
        model=WalletCredential,
        list_fields=("id", "user_id", "wallet_address", "api_key_configured", "is_configured", "is_active", "updated_at"),
        detail_fields=tuple(WALLET_MASKED_FIELDS),
        row_transform=lambda row, detail: masked_wallet_row(row) if detail else masked_wallet_list_row(row),
    ),
}


def get_table(name: str) -> AdminTable | None:
    return TABLES.get(name)


def all_tables() -> list[AdminTable]:
    return list(TABLES.values())
