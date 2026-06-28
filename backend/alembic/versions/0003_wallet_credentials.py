"""wallet credentials

Revision ID: 0003_wallet_credentials
Revises: 0002_redeem_records
Create Date: 2026-06-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_wallet_credentials"
down_revision: str | None = "0002_redeem_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wallet_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wallet_address", sa.String(length=64), nullable=False),
        sa.Column("funder_address", sa.String(length=64), nullable=True),
        sa.Column("signature_type", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("encrypted_api_secret", sa.Text(), nullable=True),
        sa.Column("encrypted_api_passphrase", sa.Text(), nullable=True),
        sa.Column("api_credentials_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_configured", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_wallet_credentials_active_singleton",
        "wallet_credentials",
        ["is_active"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_wallet_credentials_active_singleton", table_name="wallet_credentials")
    op.drop_table("wallet_credentials")
