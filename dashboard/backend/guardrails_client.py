import json
from typing import Any

import httpx


class GuardrailsClient:
    """Thin async client for a running guardrails server."""

    def __init__(self, base_url: str, http: httpx.AsyncClient):
        self._base = base_url.rstrip("/")
        self._http = http

    async def _get_json(self, path: str) -> Any | None:
        try:
            resp = await self._http.get(f"{self._base}{path}")
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None

    async def health(self) -> dict | None:
        return await self._get_json("/v1/health")

    async def configs(self) -> list | None:
        return await self._get_json("/v1/rails/configs")

    async def models(self) -> Any | None:
        return await self._get_json("/v1/models")

    async def challenges(self) -> list | None:
        return await self._get_json("/v1/challenges")

    async def admin_capabilities(self) -> dict | None:
        return await self._get_json("/v1/admin/capabilities")

    async def admin_reload(self, config_id: str | None = None) -> dict | None:
        try:
            resp = await self._http.post(
                f"{self._base}/v1/admin/reload",
                content=json.dumps({"config_id": config_id}),
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None
