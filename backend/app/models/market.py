from typing import Any

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, json_type


class Market(TimestampMixin, Base):
    __tablename__ = "markets"
    __table_args__ = (
        Index("ix_markets_start_ts_end_ts", "start_ts", "end_ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    market_slug: Mapped[str | None] = mapped_column(String(255))
    condition_id: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str | None] = mapped_column(String(1024))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_ts: Mapped[int | None] = mapped_column(Integer)
    end_ts: Mapped[int | None] = mapped_column(Integer)
    up_token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    down_token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_event: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)
    raw_market: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)

    orderbook_snapshots = relationship("OrderbookSnapshot", back_populates="market")
    strategy_decisions = relationship("StrategyDecision", back_populates="market")
    orders = relationship("Order", back_populates="market")
    settlements = relationship("Settlement", back_populates="market")
    redeem_records = relationship("RedeemRecord", back_populates="market")
