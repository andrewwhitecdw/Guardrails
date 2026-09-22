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

import httpx
import pytest
import respx
from backend.guardrails_client import GuardrailsClient

BASE = "http://guardrails:8000"


@pytest.fixture
async def client():
    http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    yield GuardrailsClient(BASE, http)
    await http.aclose()


@respx.mock
async def test_health_ok(client):
    respx.get(f"{BASE}/v1/health").mock(return_value=httpx.Response(200, json={"status": "pass"}))
    assert await client.health() == {"status": "pass"}


@respx.mock
async def test_health_unreachable_returns_none(client):
    respx.get(f"{BASE}/v1/health").mock(side_effect=httpx.ConnectError("refused"))
    assert await client.health() is None


@respx.mock
async def test_configs_and_models_and_challenges(client):
    respx.get(f"{BASE}/v1/rails/configs").mock(return_value=httpx.Response(200, json=[{"id": "demo"}]))
    respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(200, json={"data": [{"id": "gpt-4"}]}))
    respx.get(f"{BASE}/v1/challenges").mock(return_value=httpx.Response(200, json=[{"name": "c1"}]))
    assert await client.configs() == [{"id": "demo"}]
    assert await client.models() == {"data": [{"id": "gpt-4"}]}
    assert await client.challenges() == [{"name": "c1"}]


@respx.mock
async def test_admin_capabilities_probe(client):
    respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(200, json={"admin": True}))
    assert await client.admin_capabilities() == {"admin": True}

    respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(404))
    assert await client.admin_capabilities() is None

    respx.get(f"{BASE}/v1/admin/capabilities").mock(side_effect=httpx.ConnectError("refused"))
    assert await client.admin_capabilities() is None


@respx.mock
async def test_admin_reload_posts_config_id(client):
    route = respx.post(f"{BASE}/v1/admin/reload").mock(return_value=httpx.Response(200, json={"reloaded": ["demo"]}))
    result = await client.admin_reload("demo")
    assert result == {"reloaded": ["demo"]}
    assert route.calls.last.request.content == b'{"config_id": "demo"}'
