from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Literal

import httpx

from app.services.polymarket_errors import (
    POLYMARKET_CLOB_HTTP_ERROR,
    POLYMARKET_CLOB_NETWORK_ERROR,
    POLYMARKET_CLOB_TIMEOUT,
    POLYMARKET_GAMMA_HTTP_ERROR,
    POLYMARKET_GAMMA_NETWORK_ERROR,
    POLYMARKET_GAMMA_TIMEOUT,
    POLYMARKET_INVALID_RESPONSE,
    PolymarketHttpError,
)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


async def request_json_with_retries(
    *,
    client: httpx.AsyncClient,
    method: str,
    url: str,
    service_name: Literal["clob", "gamma"],
    max_retries: int,
    base_delay_seconds: float,
    logger: logging.Logger,
    **kwargs: Any,
) -> Any:
    total_attempts = max_retries + 1
    last_error: Exception | None = None

    for attempt in range(total_attempts):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise httpx.HTTPStatusError(
                    f"Retryable HTTP status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            try:
                return response.json()
            except ValueError as exc:
                raise PolymarketHttpError(
                    code=POLYMARKET_INVALID_RESPONSE,
                    message="Polymarket returned a response that was not valid JSON.",
                    endpoint=url,
                    status_code=response.status_code,
                    technical_detail=str(exc),
                ) from exc
        except PolymarketHttpError:
            raise
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code not in RETRYABLE_STATUS_CODES:
                raise _http_error(service_name, url, exc) from exc
            if attempt >= max_retries:
                raise _http_error(service_name, url, exc) from exc
            await _sleep_before_retry(
                logger=logger,
                service_name=service_name,
                method=method,
                url=url,
                attempt=attempt,
                max_retries=max_retries,
                base_delay_seconds=base_delay_seconds,
                error_type=type(exc).__name__,
            )
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            last_error = exc
            if attempt >= max_retries:
                raise _timeout_error(service_name, url, exc) from exc
            await _sleep_before_retry(
                logger=logger,
                service_name=service_name,
                method=method,
                url=url,
                attempt=attempt,
                max_retries=max_retries,
                base_delay_seconds=base_delay_seconds,
                error_type=type(exc).__name__,
            )
        except httpx.NetworkError as exc:
            last_error = exc
            if attempt >= max_retries:
                raise _network_error(service_name, url, exc) from exc
            await _sleep_before_retry(
                logger=logger,
                service_name=service_name,
                method=method,
                url=url,
                attempt=attempt,
                max_retries=max_retries,
                base_delay_seconds=base_delay_seconds,
                error_type=type(exc).__name__,
            )

    assert last_error is not None
    raise _network_error(service_name, url, last_error)


async def _sleep_before_retry(
    *,
    logger: logging.Logger,
    service_name: str,
    method: str,
    url: str,
    attempt: int,
    max_retries: int,
    base_delay_seconds: float,
    error_type: str,
) -> None:
    delay = base_delay_seconds * (2**attempt)
    jitter = random.uniform(0, base_delay_seconds / 4) if base_delay_seconds > 0 else 0
    logger.warning(
        "polymarket_http_retry",
        extra={
            "service_name": service_name,
            "method": method,
            "url": url,
            "attempt": attempt + 1,
            "max_retries": max_retries,
            "error_type": error_type,
        },
    )
    await asyncio.sleep(delay + jitter)


def _timeout_error(service_name: str, endpoint: str, exc: Exception) -> PolymarketHttpError:
    if service_name == "clob":
        return PolymarketHttpError(
            code=POLYMARKET_CLOB_TIMEOUT,
            message="The backend could not fetch the latest orderbook from Polymarket before the timeout.",
            endpoint=endpoint,
            technical_detail=str(exc),
        )
    return PolymarketHttpError(
        code=POLYMARKET_GAMMA_TIMEOUT,
        message="The backend could not fetch market metadata from Polymarket Gamma before the timeout.",
        endpoint=endpoint,
        technical_detail=str(exc),
    )


def _network_error(service_name: str, endpoint: str, exc: Exception) -> PolymarketHttpError:
    code = POLYMARKET_CLOB_NETWORK_ERROR if service_name == "clob" else POLYMARKET_GAMMA_NETWORK_ERROR
    source = "CLOB" if service_name == "clob" else "Gamma"
    return PolymarketHttpError(
        code=code,
        message=f"The backend could not reach Polymarket {source}.",
        endpoint=endpoint,
        technical_detail=str(exc),
    )


def _http_error(service_name: str, endpoint: str, exc: httpx.HTTPStatusError) -> PolymarketHttpError:
    code = POLYMARKET_CLOB_HTTP_ERROR if service_name == "clob" else POLYMARKET_GAMMA_HTTP_ERROR
    source = "CLOB" if service_name == "clob" else "Gamma"
    return PolymarketHttpError(
        code=code,
        message=f"Polymarket {source} returned HTTP {exc.response.status_code}.",
        endpoint=endpoint,
        status_code=exc.response.status_code,
        technical_detail=str(exc),
    )
