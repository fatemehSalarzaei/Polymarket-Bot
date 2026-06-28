from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, json_type


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (Index("ix_settlements_user_market", "user_id", "market_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    winning_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    btc_start_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    btc_end_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paper_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    real_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    raw_resolution: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)

    market = relationship("Market", back_populates="settlements")
    redeem_records = relationship("RedeemRecord", back_populates="settlement")
