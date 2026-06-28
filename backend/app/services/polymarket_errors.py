from __future__ import annotations


class PolymarketHttpError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        endpoint: str,
        status_code: int | None = None,
        technical_detail: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.endpoint = endpoint
        self.status_code = status_code
        self.technical_detail = technical_detail
        super().__init__(technical_detail or f"{code}: {message}")


POLYMARKET_CLOB_TIMEOUT = "POLYMARKET_CLOB_TIMEOUT"
POLYMARKET_GAMMA_TIMEOUT = "POLYMARKET_GAMMA_TIMEOUT"
POLYMARKET_CLOB_HTTP_ERROR = "POLYMARKET_CLOB_HTTP_ERROR"
POLYMARKET_GAMMA_HTTP_ERROR = "POLYMARKET_GAMMA_HTTP_ERROR"
POLYMARKET_CLOB_NETWORK_ERROR = "POLYMARKET_CLOB_NETWORK_ERROR"
POLYMARKET_GAMMA_NETWORK_ERROR = "POLYMARKET_GAMMA_NETWORK_ERROR"
POLYMARKET_INVALID_RESPONSE = "POLYMARKET_INVALID_RESPONSE"

