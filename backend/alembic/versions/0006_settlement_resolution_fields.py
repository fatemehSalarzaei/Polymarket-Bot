"""add explicit settlement resolution fields"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

from app.db.base import json_type


revision: str = "0006_settlement_resolution_fields"
down_revision: str | None = "0005_bot_running"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settlements",
        sa.Column("official_resolution_status", sa.String(length=32), nullable=False, server_default="internal_only"),
    )
    op.add_column("settlements", sa.Column("official_winning_outcome", sa.String(length=16), nullable=True))
    op.add_column("settlements", sa.Column("internal_winning_outcome", sa.String(length=16), nullable=True))
    op.add_column(
        "settlements",
        sa.Column(
            "resolution_source",
            sa.String(length=64),
            nullable=False,
            server_default="internal_chainlink_calculation",
        ),
    )
    op.add_column("settlements", sa.Column("official_resolution_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "settlements",
        sa.Column("official_resolution_raw_response", json_type, nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("settlements", "official_resolution_raw_response")
    op.drop_column("settlements", "official_resolution_checked_at")
    op.drop_column("settlements", "resolution_source")
    op.drop_column("settlements", "internal_winning_outcome")
    op.drop_column("settlements", "official_winning_outcome")
    op.drop_column("settlements", "official_resolution_status")
