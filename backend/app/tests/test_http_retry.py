import logging

import httpx
import pytest

from app.services.http_retry import request_json_with_retries
from app.services.polymarket_errors import PolymarketHttpError


@pytest.mark.asyncio
async def test_clob_read_timeout_is_retried() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow clob", request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://clob.test") as client:
        payload = await request_json_with_retries(
            client=client,
            method="GET",
            url="/book",
            service_name="clob",
            max_retries=1,
            base_delay_seconds=0,
            logger=logging.getLogger(__name__),
        )

    assert payload == {"ok": True}
    assert calls == 2


@pytest.mark.asyncio
async def test_clob_read_timeout_maps_to_polymarket_error_after_retries() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow clob", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://clob.test") as client:
        with pytest.raises(PolymarketHttpError) as exc:
            await request_json_with_retries(
                client=client,
                method="GET",
                url="/book",
                service_name="clob",
                max_retries=1,
                base_delay_seconds=0,
                logger=logging.getLogger(__name__),
            )

    assert exc.value.code == "POLYMARKET_CLOB_TIMEOUT"
    assert "slow clob" in str(exc.value)


@pytest.mark.asyncio
async def test_gamma_read_timeout_maps_to_gamma_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow gamma", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://gamma.test") as client:
        with pytest.raises(PolymarketHttpError) as exc:
            await request_json_with_retries(
                client=client,
                method="GET",
                url="/events/slug/btc",
                service_name="gamma",
                max_retries=0,
                base_delay_seconds=0,
                logger=logging.getLogger(__name__),
            )

    assert exc.value.code == "POLYMARKET_GAMMA_TIMEOUT"
