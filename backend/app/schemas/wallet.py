from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SIGNATURE_TYPES = {0, 1, 2, 3}


class WalletConfigureRequest(BaseModel):
    private_key: str
    funder_address: str | None = None
    signature_type: Literal[0, 1, 2, 3] = 0
    chain_id: int = 137
    derive_api_credentials: bool = True

    @field_validator("funder_address")
    @classmethod
    def normalize_funder_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class WalletResponse(BaseModel):
    configured: bool
    wallet_address: str | None = None
    funder_address: str | None = None
    signature_type: int | None = None
    chain_id: int | None = None
    api_key_configured: bool
    api_key_masked: str | None = None
    last_validated_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime | None = None


class WalletTestResponse(BaseModel):
    ok: bool
    message: str
    wallet_address: str | None = None
    api_key_configured: bool
    trading_ready: bool
    issues: list[str] = Field(default_factory=list)


class WalletTestDeriveResponse(BaseModel):
    ok: bool
    wallet_address: str
    api_key_present: bool
    secret_present: bool
    passphrase_present: bool


class WalletReadinessResponse(BaseModel):
    wallet_configured: bool
    wallet_address: str | None = None
    funder_address: str | None = None
    api_credentials_configured: bool
    private_key_decryptable: bool
    funder_address_configured: bool
    signature_type: int | None = None
    chain_id: int | None = None
    trading_ready: bool
    blocking_reasons: list[str] = Field(default_factory=list)
