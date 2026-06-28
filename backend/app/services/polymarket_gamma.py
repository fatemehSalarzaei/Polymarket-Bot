import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.http_retry import request_json_with_retries
from app.services.polymarket_errors import POLYMARKET_INVALID_RESPONSE, PolymarketHttpError


class PolymarketGammaClient:
    def __init__(
        self,
        base_url: str,
        *,
        read_timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(
            connect=settings.polymarket_http_connect_timeout,
            read=read_timeout if read_timeout is not None else settings.polymarket_http_read_timeout,
            write=settings.polymarket_http_write_timeout,
            pool=settings.polymarket_http_pool_timeout,
        )
        self._max_retries = settings.polymarket_http_max_retries if max_retries is None else max_retries
        self._base_delay_seconds = settings.polymarket_http_retry_base_delay_seconds
        self._logger = logging.getLogger(__name__)

    async def get_event_by_slug(self, slug: str) -> dict[str, Any]:
        endpoint = f"/events/slug/{slug}"
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            payload = await request_json_with_retries(
                client=client,
                method="GET",
                url=endpoint,
                service_name="gamma",
                max_retries=self._max_retries,
                base_delay_seconds=self._base_delay_seconds,
                logger=self._logger,
            )

        if not isinstance(payload, dict):
            raise PolymarketHttpError(
                code=POLYMARKET_INVALID_RESPONSE,
                message="Polymarket Gamma returned a response that was not a JSON object.",
                endpoint=endpoint,
                technical_detail="Gamma event response must be a JSON object",
            )
        return payload
