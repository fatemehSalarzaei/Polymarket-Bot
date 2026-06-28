"""add redeem records

Revision ID: 0002_redeem_records
Revises: 0001_initial_schema
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_redeem_records"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "redeem_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("settlement_id", sa.Integer(), nullable=True),
        sa.Column("condition_id", sa.String(length=255), nullable=False),
        sa.Column("winning_outcome", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("tx_hash", sa.String(length=255), nullable=True),
        sa.Column("wallet_address", sa.String(length=255), nullable=True),
        sa.Column("amount_redeemed", sa.Numeric(18, 8), nullable=True),
        sa.Column("balance_before", sa.Numeric(20, 8), nullable=True),
        sa.Column("balance_after", sa.Numeric(20, 8), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("raw_request", json_type, nullable=False),
        sa.Column("raw_response", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["settlement_id"], ["settlements.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "condition_id", "mode", name="uq_redeem_market_condition_mode"),
    )
    op.create_index("ix_redeem_records_status_created", "redeem_records", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_redeem_records_status_created", table_name="redeem_records")
    op.drop_table("redeem_records")
