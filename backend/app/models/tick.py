from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, json_type, utc_now


class OrderbookSnapshot(Base):
    __tablename__ = "orderbook_snapshots"
    __table_args__ = (
        Index("ix_orderbook_snapshots_token_received", "token_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    book_hash: Mapped[str | None] = mapped_column(String(255))
    best_bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    best_ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    midpoint: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    spread: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    last_trade_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    min_order_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    neg_risk: Mapped[bool | None] = mapped_column(Boolean)
    bids: Mapped[list[dict[str, Any]]] = mapped_column(json_type, default=list, nullable=False)
    asks: Mapped[list[dict[str, Any]]] = mapped_column(json_type, default=list, nullable=False)

    market = relationship("Market", back_populates="orderbook_snapshots")


class ChainlinkTick(Base):
    __tablename__ = "chainlink_ticks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), default="btc/usd", nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    source: Mapped[str] = mapped_column(String(128), default="polymarket_rtds_chainlink", nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)

