from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    fields: tuple[str, ...] | None = None
    create_fields: tuple[str, ...] | None = None
    edit_fields: tuple[str, ...] | None = None
    row_transform: Callable[[Any], dict[str, Any]] | None = None

    @property
    def read_only(self) -> bool:
        return not self.creatable and not self.editable and not self.deletable

    def display_fields(self) -> list[str]:
        if self.fields is not None:
            return [field for field in self.fields if field not in FORBIDDEN_FIELDS]
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

    def public_row(self, row: Any) -> dict[str, Any]:
        if self.row_transform is not None:
            return self.row_transform(row)
        return {field: getattr(row, field) for field in self.display_fields()}


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


TABLES: dict[str, AdminTable] = {
    "users": AdminTable(
        name="users",
        label="Users",
        model=User,
        creatable=True,
        editable=True,
        fields=("id", "username", "email", "role", "is_active", "last_login_at", "created_at", "updated_at"),
        create_fields=("username", "email", "password", "role", "is_active"),
        edit_fields=("username", "email", "password", "role", "is_active"),
    ),
    "markets": AdminTable(name="markets", label="Markets", model=Market),
    "strategy_settings": AdminTable(
        name="strategy_settings",
        label="Strategy Settings",
        model=StrategySettings,
        editable=True,
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
    "strategy_decisions": AdminTable(name="strategy_decisions", label="Strategy Decisions", model=StrategyDecision),
    "orders": AdminTable(name="orders", label="Orders", model=Order),
    "settlements": AdminTable(name="settlements", label="Settlements", model=Settlement),
    "redeem_records": AdminTable(name="redeem_records", label="Redeem Records", model=RedeemRecord),
    "audit_logs": AdminTable(name="audit_logs", label="Audit Logs", model=AuditLog),
    "wallet_credentials_masked": AdminTable(
        name="wallet_credentials_masked",
        label="Wallet Credentials",
        model=WalletCredential,
        fields=tuple(WALLET_MASKED_FIELDS),
        row_transform=masked_wallet_row,
    ),
}


def get_table(name: str) -> AdminTable | None:
    return TABLES.get(name)


def all_tables() -> list[AdminTable]:
    return list(TABLES.values())
