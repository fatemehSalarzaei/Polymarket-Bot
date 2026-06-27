from typing import Any

import httpx

from app.schemas.execution import GeoblockStatus


class GeoblockClient:
    def __init__(self, url: str = "https://polymarket.com/api/geoblock") -> None:
        self._url = url

    async def get_status(self) -> GeoblockStatus:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self._url)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            payload = {"value": payload}
        return parse_geoblock_status(payload)


def parse_geoblock_status(payload: dict[str, Any]) -> GeoblockStatus:
    blocked = bool(
        payload.get("blocked")
        or payload.get("isBlocked")
        or payload.get("restricted")
        or payload.get("is_geoblocked")
        or payload.get("geoblocked")
    )
    return GeoblockStatus(blocked=blocked, raw_response=payload)

