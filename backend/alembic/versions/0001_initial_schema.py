"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-27 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_slug", sa.String(length=255), nullable=False),
        sa.Column("market_slug", sa.String(length=255), nullable=True),
        sa.Column("condition_id", sa.String(length=255), nullable=False),
        sa.Column("question", sa.String(length=1024), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("start_ts", sa.Integer(), nullable=True),
        sa.Column("end_ts", sa.Integer(), nullable=True),
        sa.Column("up_token_id", sa.String(length=255), nullable=False),
        sa.Column("down_token_id", sa.String(length=255), nullable=False),
        sa.Column("raw_event", json_type, nullable=False),
        sa.Column("raw_market", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_slug"),
    )
    op.create_index("ix_markets_start_ts_end_ts", "markets", ["start_ts", "end_ts"])

    op.create_table(
        "chainlink_ticks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(20, 8), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", json_type, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "strategy_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("paper_trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("trading_enabled", sa.Boolean(), nullable=False),
        sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
        sa.Column("final_window_seconds", sa.Integer(), nullable=False),
        sa.Column("min_edge", sa.Numeric(8, 4), nullable=False),
        sa.Column("max_spread", sa.Numeric(8, 4), nullable=False),
        sa.Column("max_slippage", sa.Numeric(8, 4), nullable=False),
        sa.Column("max_order_size_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_daily_loss_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_data_age_seconds", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("before", json_type, nullable=True),
        sa.Column("after", json_type, nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "orderbook_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("token_id", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("book_hash", sa.String(length=255), nullable=True),
        sa.Column("best_bid", sa.Numeric(18, 8), nullable=True),
        sa.Column("best_ask", sa.Numeric(18, 8), nullable=True),
        sa.Column("midpoint", sa.Numeric(18, 8), nullable=True),
        sa.Column("spread", sa.Numeric(18, 8), nullable=True),
        sa.Column("last_trade_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("min_order_size", sa.Numeric(18, 8), nullable=True),
        sa.Column("tick_size", sa.Numeric(18, 8), nullable=True),
        sa.Column("neg_risk", sa.Boolean(), nullable=True),
        sa.Column("bids", json_type, nullable=False),
        sa.Column("asks", json_type, nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orderbook_snapshots_token_received",
        "orderbook_snapshots",
        ["token_id", "received_at"],
    )

    op.create_table(
        "strategy_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("time_remaining_seconds", sa.Integer(), nullable=True),
        sa.Column("btc_start_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("current_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("delta", sa.Numeric(20, 8), nullable=True),
        sa.Column("up_bid", sa.Numeric(18, 8), nullable=True),
        sa.Column("up_ask", sa.Numeric(18, 8), nullable=True),
        sa.Column("down_bid", sa.Numeric(18, 8), nullable=True),
        sa.Column("down_ask", sa.Numeric(18, 8), nullable=True),
        sa.Column("estimated_probability", sa.Numeric(18, 8), nullable=True),
        sa.Column("market_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("edge", sa.Numeric(18, 8), nullable=True),
        sa.Column("spread", sa.Numeric(18, 8), nullable=True),
        sa.Column("risk_passed", sa.Boolean(), nullable=False),
        sa.Column("risk_reasons", json_type, nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("raw_context", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_strategy_decisions_market_created",
        "strategy_decisions",
        ["market_id", "created_at"],
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("strategy_decision_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("external_order_id", sa.String(length=255), nullable=True),
        sa.Column("token_id", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Numeric(18, 8), nullable=False),
        sa.Column("size", sa.Numeric(18, 8), nullable=False),
        sa.Column("size_matched", sa.Numeric(18, 8), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_response", json_type, nullable=False),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.ForeignKeyConstraint(["strategy_decision_id"], ["strategy_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_mode_status_submitted", "orders", ["mode", "status", "submitted_at"])

    op.create_table(
        "settlements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("winning_outcome", sa.String(length=16), nullable=False),
        sa.Column("btc_start_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("btc_end_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paper_pnl", sa.Numeric(18, 8), nullable=True),
        sa.Column("real_pnl", sa.Numeric(18, 8), nullable=True),
        sa.Column("raw_resolution", json_type, nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    strategy_settings = sa.table(
        "strategy_settings",
        sa.column("paper_trading_enabled", sa.Boolean),
        sa.column("trading_enabled", sa.Boolean),
        sa.column("kill_switch_active", sa.Boolean),
        sa.column("final_window_seconds", sa.Integer),
        sa.column("min_edge", sa.Numeric),
        sa.column("max_spread", sa.Numeric),
        sa.column("max_slippage", sa.Numeric),
        sa.column("max_order_size_usd", sa.Numeric),
        sa.column("max_daily_loss_usd", sa.Numeric),
        sa.column("max_data_age_seconds", sa.Integer),
        sa.column("order_type", sa.String),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        strategy_settings,
        [
            {
                "paper_trading_enabled": True,
                "trading_enabled": False,
                "kill_switch_active": False,
                "final_window_seconds": 180,
                "min_edge": 0.05,
                "max_spread": 0.03,
                "max_slippage": 0.02,
                "max_order_size_usd": 1,
                "max_daily_loss_usd": 1,
                "max_data_age_seconds": 10,
                "order_type": "FAK",
                "updated_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("settlements")
    op.drop_index("ix_orders_mode_status_submitted", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_strategy_decisions_market_created", table_name="strategy_decisions")
    op.drop_table("strategy_decisions")
    op.drop_index("ix_orderbook_snapshots_token_received", table_name="orderbook_snapshots")
    op.drop_table("orderbook_snapshots")
    op.drop_table("audit_logs")
    op.drop_table("strategy_settings")
    op.drop_table("chainlink_ticks")
    op.drop_index("ix_markets_start_ts_end_ts", table_name="markets")
    op.drop_table("markets")
