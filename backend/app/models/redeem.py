from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, json_type


class RedeemRecord(TimestampMixin, Base):
    __tablename__ = "redeem_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "market_id",
            "condition_id",
            "wallet_credential_id",
            "mode",
            name="uq_redeem_user_market_condition_wallet_mode",
        ),
        Index("ix_redeem_records_status_created", "status", "created_at"),
        Index("ix_redeem_records_user_market_condition", "user_id", "market_id", "condition_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    wallet_credential_id: Mapped[int | None] = mapped_column(ForeignKey("wallet_credentials.id"))
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), nullable=False)
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlements.id"))
    condition_id: Mapped[str] = mapped_column(String(255), nullable=False)
    winning_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="real", nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(255))
    wallet_address: Mapped[str | None] = mapped_column(String(255))
    amount_redeemed: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    balance_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    error_message: Mapped[str | None] = mapped_column(String(1024))
    raw_request: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(json_type, default=dict, nullable=False)
    market = relationship("Market", back_populates="redeem_records")
    settlement = relationship("Settlement", back_populates="redeem_records")
