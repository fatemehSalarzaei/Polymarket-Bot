from __future__ import annotations

from typing import Protocol

from app.schemas.execution import PlaceOrderRequest, PlaceOrderResult


class ClobTradingClient(Protocol):
    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        ...


class BackendOnlyClobSdkWrapper:
    def __init__(self, *, credentials_configured: bool, sdk_client: ClobTradingClient | None = None) -> None:
        self.credentials_configured = credentials_configured
        self._sdk_client = sdk_client

    async def place_order(self, request: PlaceOrderRequest) -> PlaceOrderResult:
        if not self.credentials_configured:
            return PlaceOrderResult(
                submitted=False,
                status="FAILED",
                raw_response={},
                error_message="CREDENTIALS_MISSING",
            )
        if self._sdk_client is None:
            return PlaceOrderResult(
                submitted=False,
                status="FAILED",
                raw_response={},
                error_message="SDK_CLIENT_NOT_CONFIGURED",
            )
        return await self._sdk_client.place_order(request)

