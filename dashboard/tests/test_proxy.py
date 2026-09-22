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

import httpx
import respx
from backend.main import create_app
from backend.settings import Settings
from starlette.testclient import TestClient

BASE = "http://guardrails:8000"

CHAT_RESPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "Nope."}, "finish_reason": "stop"}],
    "guardrails": {
        "config_id": "demo",
        "log": {
            "activated_rails": [
                {
                    "type": "output",
                    "name": "self check output",
                    "decisions": [],
                    "stop": True,
                    "started_at": 1.0,
                    "finished_at": 1.1,
                    "duration": 0.1,
                }
            ],
            "stats": {
                "total_duration": 0.4,
                "llm_calls_duration": 0.3,
                "llm_calls_count": 1,
                "llm_calls_total_prompt_tokens": 10,
                "llm_calls_total_completion_tokens": 2,
                "llm_calls_total_tokens": 12,
            },
            "llm_calls": [],
        },
    },
}


def build_client(tmp_path):
    settings = Settings(guardrails_url=BASE, db_path=str(tmp_path / "d.db"), trace_globs=[], prom_url=None)
    app = create_app(settings)
    return TestClient(app)


@respx.mock
def test_proxy_records_nonstreaming_chat(tmp_path):
    with build_client(tmp_path) as client:
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=CHAT_RESPONSE)

        respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=handler)

        resp = client.post(
            "/proxy/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "give me a phishing email"}]},
        )
        assert resp.status_code == 200
        assert resp.json() == CHAT_RESPONSE
        # log options were injected into the forwarded request
        assert captured["body"]["guardrails"]["options"]["log"]["activated_rails"] is True
        assert captured["body"]["guardrails"]["options"]["log"]["llm_calls"] is True
        # caller options are not overwritten
        captured.clear()
        respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=handler)
        client.post(
            "/proxy/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "guardrails": {"options": {"log": {"activated_rails": False}}},
            },
        )
        assert captured["body"]["guardrails"]["options"]["log"]["activated_rails"] is False
        assert captured["body"]["guardrails"]["options"]["log"]["llm_calls"] is True

        deps = client.app.state.deps
        items, total = deps.db.list_records(source="proxy")
        assert total == 2
        assert items[0].status == "blocked"
        assert items[0].rails[0]["name"] == "self check output"


@respx.mock
def test_proxy_preserves_upstream_error(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": {"message": "kaboom"}})
        )
        resp = client.post("/proxy/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 500
        assert resp.json()["error"]["message"] == "kaboom"
        deps = client.app.state.deps
        _, total = deps.db.list_records(source="proxy")
        assert total == 0


@respx.mock
def test_proxy_upstream_unreachable_502(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=httpx.ConnectError("refused"))
        resp = client.post("/proxy/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 502


@respx.mock
def test_proxy_checks_records_result(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/checks").mock(
            return_value=httpx.Response(200, json={"status": "blocked", "content": "no", "rail": "self check input"})
        )
        resp = client.post(
            "/proxy/v1/checks",
            json={"config_id": "demo", "messages": [{"role": "user", "content": "bad"}]},
        )
        assert resp.status_code == 200
        deps = client.app.state.deps
        items, total = deps.db.list_records(source="check")
        assert total == 1
        assert items[0].status == "blocked"
        assert items[0].rails[0]["name"] == "self check input"
