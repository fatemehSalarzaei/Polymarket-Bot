from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utc_now


class StrategySettings(Base):
    __tablename__ = "strategy_settings"
    __table_args__ = (Index("ix_strategy_settings_user_id", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    paper_trading_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_running: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final_window_seconds: Mapped[int] = mapped_column(default=180, nullable=False)
    min_edge: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.05"), nullable=False)
    max_spread: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.03"), nullable=False)
    max_slippage: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0.02"), nullable=False)
    max_order_size_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("1"), nullable=False)
    max_daily_loss_usd: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("1"), nullable=False)
    max_data_age_seconds: Mapped[int] = mapped_column(default=10, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), default="FAK", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
