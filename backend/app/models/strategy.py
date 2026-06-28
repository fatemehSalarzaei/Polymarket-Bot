from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, json_type, utc_now


class StrategyDecision(Base):
    __tablename__ = "strategy_decisions"
    __table_args__ = (
        Index("ix_strategy_decisions_market_created", "market_id", "created_at"),
        Index("ix_strategy_decisions_user_market", "user_id", "market_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16), default="paper", nullable=False)
    time_remaining_seconds: Mapped[int | None] = mapped_column(Integer)
    btc_start_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    up_bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    up_ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    down_bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    down_ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    estimated_probability: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    edge: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    spread: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    risk_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    risk_reasons: Mapped[list[str]] = mapped_column(json_type, default=list, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    raw_context: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    market = relationship("Market", back_populates="strategy_decisions")
    orders = relationship("Order", back_populates="strategy_decision")
