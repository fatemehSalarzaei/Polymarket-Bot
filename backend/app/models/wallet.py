from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class WalletCredential(TimestampMixin, Base):
    __tablename__ = "wallet_credentials"
    __table_args__ = (Index("ix_wallet_credentials_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False)
    funder_address: Mapped[str | None] = mapped_column(String(128))
    signature_type: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    chain_id: Mapped[int] = mapped_column(Integer, default=137, nullable=False)
    encrypted_private_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    encrypted_api_secret: Mapped[str | None] = mapped_column(Text)
    encrypted_api_passphrase: Mapped[str | None] = mapped_column(Text)
    api_credentials_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
