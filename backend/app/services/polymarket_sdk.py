from __future__ import annotations

import asyncio
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.execution import PlaceOrderRequest, PlaceOrderResult
from app.services.wallet_credentials import TradingCredentialBundle, get_active_wallet_credentials_for_trading


class ClobTradingClient(Protocol):
    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        ...

    async def get_order(self, order_id: str) -> dict:
        ...


class BackendOnlyClobSdkWrapper:
    def __init__(
        self,
        *,
        credentials_configured: bool,
        sdk_client: ClobTradingClient | None = None,
        wallet_configured: bool | None = None,
        api_credentials_configured: bool | None = None,
    ) -> None:
        self.wallet_configured = credentials_configured if wallet_configured is None else wallet_configured
        self.api_credentials_configured = (
            credentials_configured if api_credentials_configured is None else api_credentials_configured
        )
        self.credentials_configured = self.wallet_configured and self.api_credentials_configured
        self._sdk_client = sdk_client

    @property
    def credentials_missing_reason(self) -> str | None:
        if not self.wallet_configured:
            return "WALLET_CONFIG_MISSING"
        if not self.api_credentials_configured:
            return "WALLET_API_CREDENTIALS_MISSING"
        return None

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if not self.credentials_configured:
            return PlaceOrderResult(
                submitted=False,
                status="FAILED",
                raw_response={},
                error_message=self.credentials_missing_reason or "WALLET_API_CREDENTIALS_MISSING",
            )
        if self._sdk_client is None:
            return PlaceOrderResult(
                submitted=False,
                status="FAILED",
                raw_response={},
                error_message="SDK_CLIENT_NOT_CONFIGURED",
            )
        return await self._sdk_client.place_order(request)

    async def get_order(self, order_id: str) -> dict:
        if not self.credentials_configured:
            return {"status": "FAILED", "error": self.credentials_missing_reason or "WALLET_API_CREDENTIALS_MISSING"}
        if self._sdk_client is None or not hasattr(self._sdk_client, "get_order"):
            return {"status": "FAILED", "error": "SDK_CLIENT_NOT_CONFIGURED"}
        return await self._sdk_client.get_order(order_id)


class PolymarketOrderSdkClient:
    def __init__(self, bundle: TradingCredentialBundle) -> None:
        self._bundle = bundle

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        return await asyncio.to_thread(self._place_order_sync, request)

    async def get_order(self, order_id: str) -> dict:
        return await asyncio.to_thread(self._get_order_sync, order_id)

    def _place_order_sync(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        try:
            from py_clob_client.client import ClobClient  # type: ignore
            from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType  # type: ignore
            from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore
        except ImportError as exc:
            return PlaceOrderResult(
                submitted=False,
                status="FAILED",
                raw_response={},
                error_message=f"SDK_IMPORT_FAILED:{type(exc).__name__}",
            )

        settings = get_settings()
        try:
            client = ClobClient(
                host=str(settings.polymarket_clob_host),
                key=self._bundle.private_key,
                chain_id=self._bundle.chain_id,
                signature_type=self._bundle.signature_type,
                funder=self._bundle.funder_address,
            )
            client.set_api_creds(
                ApiCreds(
                    api_key=self._bundle.api_key,
                    api_secret=self._bundle.api_secret,
                    api_passphrase=self._bundle.api_passphrase,
                )
            )
            signed_order = client.create_order(
                OrderArgs(
                    token_id=request.token_id,
                    price=float(request.price),
                    size=float(request.size),
                    side=BUY if request.side == "BUY" else SELL,
                )
            )
            response = client.post_order(signed_order, orderType=_sdk_order_type(OrderType, request.order_type))
        except Exception as exc:
            return PlaceOrderResult(
                submitted=False,
                status="FAILED",
                raw_response={},
                error_message=_safe_sdk_error(exc, self._bundle),
            )

        raw_response = response if isinstance(response, dict) else {"response": str(response)}
        external_order_id = str(raw_response.get("orderID") or raw_response.get("order_id") or raw_response.get("id") or "")
        return PlaceOrderResult(
            submitted=True,
            status="SUBMITTED",
            external_order_id=external_order_id or None,
            raw_response=raw_response,
        )

    def _get_order_sync(self, order_id: str) -> dict:
        try:
            from py_clob_client.client import ClobClient  # type: ignore
            from py_clob_client.clob_types import ApiCreds  # type: ignore
        except ImportError as exc:
            return {"status": "FAILED", "error": f"SDK_IMPORT_FAILED:{type(exc).__name__}"}

        settings = get_settings()
        try:
            client = ClobClient(
                host=str(settings.polymarket_clob_host),
                key=self._bundle.private_key,
                chain_id=self._bundle.chain_id,
                signature_type=self._bundle.signature_type,
                funder=self._bundle.funder_address,
            )
            client.set_api_creds(
                ApiCreds(
                    api_key=self._bundle.api_key,
                    api_secret=self._bundle.api_secret,
                    api_passphrase=self._bundle.api_passphrase,
                )
            )
            response = client.get_order(order_id)
        except Exception as exc:
            return {"status": "FAILED", "error": _safe_sdk_error(exc, self._bundle)}
        return response if isinstance(response, dict) else {"response": str(response)}


async def build_clob_sdk_from_stored_wallet(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    sdk_client_factory=None,
) -> BackendOnlyClobSdkWrapper:
    try:
        bundle = await get_active_wallet_credentials_for_trading(session, user_id=user_id)
    except AppError as exc:
        if exc.code == "WALLET_CONFIG_MISSING":
            return BackendOnlyClobSdkWrapper(
                credentials_configured=False,
                wallet_configured=False,
                api_credentials_configured=False,
            )
        if exc.code == "WALLET_API_CREDENTIALS_MISSING":
            return BackendOnlyClobSdkWrapper(
                credentials_configured=False,
                wallet_configured=True,
                api_credentials_configured=False,
            )
        raise
    sdk_client = sdk_client_factory(bundle) if sdk_client_factory is not None else PolymarketOrderSdkClient(bundle)
    return BackendOnlyClobSdkWrapper(credentials_configured=True, sdk_client=sdk_client)


def stored_wallet_bundle_to_sdk_config(bundle: TradingCredentialBundle) -> dict[str, object]:
    return {
        "private_key": bundle.private_key,
        "wallet_address": bundle.wallet_address,
        "funder_address": bundle.funder_address,
        "signature_type": bundle.signature_type,
        "chain_id": bundle.chain_id,
        "api_key": bundle.api_key,
        "api_secret": bundle.api_secret,
        "api_passphrase": bundle.api_passphrase,
    }


def _sdk_order_type(order_type_enum, order_type: str):
    return getattr(order_type_enum, order_type, order_type)


def _safe_sdk_error(exc: Exception, bundle: TradingCredentialBundle | None = None) -> str:
    text = str(exc)
    settings = get_settings()
    secrets = [
        settings.private_key,
        settings.polymarket_api_key,
        settings.polymarket_api_secret,
        settings.polymarket_api_passphrase,
    ]
    if bundle is not None:
        secrets.extend([bundle.private_key, bundle.api_key, bundle.api_secret, bundle.api_passphrase])
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text[:500] or type(exc).__name__
