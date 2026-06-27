from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, json_type, utc_now


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_mode_status_submitted", "mode", "status", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    strategy_decision_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_decisions.id"))
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    external_order_id: Mapped[str | None] = mapped_column(String(255))
    token_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    size_matched: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_response: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(1024))

    market = relationship("Market", back_populates="orders")
    strategy_decision = relationship("StrategyDecision", back_populates="orders")

