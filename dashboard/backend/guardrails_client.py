# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
