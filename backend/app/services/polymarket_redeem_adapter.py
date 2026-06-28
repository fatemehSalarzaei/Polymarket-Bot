from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.core.config import Settings, get_settings


@dataclass
class RedeemAdapterResult:
    submitted: bool
    confirmed: bool = False
    dry_run: bool = False
    tx_hash: str | None = None
    amount_redeemed: Decimal | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None


class PolymarketRedeemAdapter(Protocol):
    credentials_configured: bool
    wallet_address: str | None

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult: ...

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None: ...


class SafeDryRunRedeemAdapter:
    credentials_configured = True

    def __init__(self, *, wallet_address: str | None = None) -> None:
        self.wallet_address = wallet_address

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        return RedeemAdapterResult(
            submitted=False,
            confirmed=False,
            dry_run=True,
            raw_response={
                "dry_run": True,
                "condition_id": condition_id,
                "index_sets": index_sets,
                "message": "Redeem dry-run active; no blockchain transaction submitted.",
            },
            error_message="REDEEM_DRY_RUN",
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        return None


class BackendOnlyPolymarketRedeemAdapter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self.wallet_address = self._settings.polymarket_funder_address or None
        self.credentials_configured = bool(
            self._settings.private_key
            and self._settings.polymarket_api_key
            and self._settings.polymarket_api_secret
            and self._settings.polymarket_api_passphrase
            and self._settings.polymarket_funder_address
        )

    async def redeem(self, condition_id: str, index_sets: list[int]) -> RedeemAdapterResult:
        raise NotImplementedError(
            "Real Polymarket CTF redeem requires a configured web3/SDK provider for redeemPositions; "
            "dry-run is supported, but non-dry-run redemption is intentionally not implemented."
        )

    async def get_pusd_balance(self, wallet_address: str) -> Decimal | None:
        return None


def build_redeem_adapter(settings: Settings | None = None) -> PolymarketRedeemAdapter:
    config = settings or get_settings()
    if config.redeem_dry_run or config.real_order_dry_run:
        return SafeDryRunRedeemAdapter(wallet_address=config.polymarket_funder_address or None)
    return BackendOnlyPolymarketRedeemAdapter(config)
