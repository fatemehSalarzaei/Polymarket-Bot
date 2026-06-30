"""add persistent bot running gate

Revision ID: 0005_bot_running
Revises: 0004_multi_user_foundation
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_bot_running"
down_revision: str | None = "0004_multi_user_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_settings",
        sa.Column("bot_running", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("strategy_settings", "bot_running")
