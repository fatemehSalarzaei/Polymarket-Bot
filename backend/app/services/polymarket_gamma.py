from typing import Any

import httpx


class PolymarketGammaClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def get_event_by_slug(self, slug: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=10) as client:
            response = await client.get(f"/events/slug/{slug}")
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Gamma event response must be a JSON object")
        return payload

