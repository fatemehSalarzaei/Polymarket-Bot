"""multi user foundation

Revision ID: 0004_multi_user_foundation
Revises: 0003_wallet_credentials
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_multi_user_foundation"
down_revision: str | None = "0003_wallet_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="trader"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    _add_user_column("wallet_credentials")
    _add_user_column("strategy_settings")
    _add_user_column("strategy_decisions")
    _add_user_column("orders")
    _add_user_column("settlements")
    _add_user_column("redeem_records")
    _add_user_column("audit_logs")
    op.add_column("orders", sa.Column("wallet_credential_id", sa.Integer(), nullable=True))
    op.add_column("redeem_records", sa.Column("wallet_credential_id", sa.Integer(), nullable=True))
    op.add_column("audit_logs", sa.Column("actor_user_id", sa.Integer(), nullable=True))
    op.add_column("audit_logs", sa.Column("actor_role", sa.String(length=32), nullable=True))

    op.create_index("ix_wallet_credentials_user_id", "wallet_credentials", ["user_id"])
    op.create_index("ix_strategy_settings_user_id", "strategy_settings", ["user_id"], unique=True)
    op.create_index("ix_strategy_decisions_user_market", "strategy_decisions", ["user_id", "market_id"])
    op.create_index("ix_orders_user_market", "orders", ["user_id", "market_id"])
    op.create_index("ix_settlements_user_market", "settlements", ["user_id", "market_id"])
    op.create_index("ix_redeem_records_user_market_condition", "redeem_records", ["user_id", "market_id", "condition_id"])
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_index("ix_redeem_records_user_market_condition", table_name="redeem_records")
    op.drop_index("ix_settlements_user_market", table_name="settlements")
    op.drop_index("ix_orders_user_market", table_name="orders")
    op.drop_index("ix_strategy_decisions_user_market", table_name="strategy_decisions")
    op.drop_index("ix_strategy_settings_user_id", table_name="strategy_settings")
    op.drop_index("ix_wallet_credentials_user_id", table_name="wallet_credentials")
    op.drop_column("audit_logs", "actor_role")
    op.drop_column("audit_logs", "actor_user_id")
    op.drop_column("redeem_records", "wallet_credential_id")
    op.drop_column("orders", "wallet_credential_id")
    for table in (
        "audit_logs",
        "redeem_records",
        "settlements",
        "orders",
        "strategy_decisions",
        "strategy_settings",
        "wallet_credentials",
    ):
        op.drop_column(table, "user_id")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")


def _add_user_column(table_name: str) -> None:
    op.add_column(table_name, sa.Column("user_id", sa.Integer(), nullable=True))
