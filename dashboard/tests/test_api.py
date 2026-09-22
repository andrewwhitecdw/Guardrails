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
from backend.models import RequestRecord
from backend.settings import Settings
from starlette.testclient import TestClient

BASE = "http://guardrails:8000"


def build_client(tmp_path, **overrides):
    settings = Settings(
        guardrails_url=BASE,
        db_path=str(tmp_path / "d.db"),
        trace_globs=[],
        prom_url=None,
        **overrides,
    )
    return TestClient(create_app(settings))


def seed_record(db):
    db.insert_record(
        RequestRecord(
            id="r1",
            ts=5000,
            source="proxy",
            status="blocked",
            config_id="demo",
            input_summary="bad request",
            output_summary="refused",
            rails=[{"name": "self check input", "stop": True}],
            llm_calls=[{"model": "gpt-4", "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}],
            phase_durations={"total_duration": 0.5},
        )
    )


@respx.mock
def test_status_endpoint_reports_server_and_hook(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/health").mock(return_value=httpx.Response(200, json={"status": "pass"}))
        respx.get(f"{BASE}/v1/rails/configs").mock(return_value=httpx.Response(200, json=[{"id": "demo"}]))
        respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
        respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(404))

        data = client.get("/api/status").json()
        assert data["guardrails"]["healthy"] is True
        assert data["guardrails"]["configs"] == [{"id": "demo"}]
        assert data["admin_hook"] is False
        assert "ingestion" in data


@respx.mock
def test_status_when_server_down(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/health").mock(side_effect=httpx.ConnectError("refused"))
        respx.get(f"{BASE}/v1/rails/configs").mock(side_effect=httpx.ConnectError("refused"))
        respx.get(f"{BASE}/v1/models").mock(side_effect=httpx.ConnectError("refused"))
        respx.get(f"{BASE}/v1/admin/capabilities").mock(side_effect=httpx.ConnectError("refused"))

        data = client.get("/api/status").json()
        assert data["guardrails"]["healthy"] is False
        assert data["guardrails"]["configs"] is None


def test_requests_list_and_detail(tmp_path):
    with build_client(tmp_path) as client:
        seed_record(client.app.state.deps.db)
        data = client.get("/api/requests").json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "r1"
        assert data["items"][0]["status"] == "blocked"

        data = client.get("/api/requests", params={"status": "allowed"}).json()
        assert data["total"] == 0

        data = client.get("/api/requests", params={"search": "bad"}).json()
        assert data["total"] == 1

        detail = client.get("/api/requests/r1").json()
        assert detail["rails"][0]["name"] == "self check input"
        assert client.get("/api/requests/nope").status_code == 404


def test_metrics_overview_and_rails(tmp_path):
    with build_client(tmp_path) as client:
        seed_record(client.app.state.deps.db)
        params = {"start": 0, "end": 9_999_999_999_999}
        data = client.get("/api/metrics/overview", params=params).json()
        assert data["count"] == 1
        assert data["blocked"] == 1
        assert data["input_tokens"] == 1

        rails = client.get("/api/metrics/rails", params=params).json()
        assert rails[0]["name"] == "self check input"
        assert rails[0]["blocked"] == 1


def test_metrics_series(tmp_path):
    with build_client(tmp_path) as client:
        db = client.app.state.deps.db
        db.insert_samples([("guardrails_nonstream_queued", "{}", 1000, 3.0)])
        data = client.get(
            "/api/metrics/series",
            params={"name_prefix": "guardrails_nonstream", "start": 0, "end": 9_999_999_999_999},
        ).json()
        assert len(data) == 1
        assert data[0]["value"] == 3.0


def test_telemetry_endpoint(tmp_path):
    usage = tmp_path / "usage_stats.json"
    usage.write_text('{"event": "startup", "timestamp": 1.0}\n')
    with build_client(tmp_path, usage_stats_path=str(usage)) as client:
        data = client.get("/api/telemetry/events").json()
        assert data["items"] == [{"event": "startup", "timestamp": 1.0}]


CHAT_OK = {
    "choices": [{"message": {"role": "assistant", "content": "fine"}, "finish_reason": "stop"}],
    "guardrails": {
        "config_id": "demo",
        "log": {"activated_rails": [], "stats": {"total_duration": 0.2}, "llm_calls": []},
    },
}


@respx.mock
def test_console_run_records_with_console_source(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(200, json=CHAT_OK))
        resp = client.post(
            "/api/commands/console/run",
            json={"config_id": "demo", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "fine"
        items, total = client.app.state.deps.db.list_records(source="console")
        assert total == 1
        assert items[0].config_id == "demo"


@respx.mock
def test_checks_run_records_with_check_source(tmp_path):
    with build_client(tmp_path) as client:
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"status": "passed", "content": "ok", "rail": None})

        respx.post(f"{BASE}/v1/checks").mock(side_effect=handler)
        resp = client.post(
            "/api/commands/checks/run",
            json={
                "config_id": "demo",
                "rail_types": ["input"],
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        # the real /v1/checks endpoint expects config_id/rail_types nested under "guardrails"
        assert captured["body"]["guardrails"] == {"config_id": "demo", "rail_types": ["input"]}
        items, total = client.app.state.deps.db.list_records(source="check")
        assert total == 1
        assert items[0].status == "allowed"
        assert items[0].config_id == "demo"


@respx.mock
def test_challenges_list_and_run(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/challenges").mock(
            return_value=httpx.Response(200, json=[{"id": "c1", "input": "hack"}, {"id": "c2", "input": "spam"}])
        )
        assert len(client.get("/api/commands/challenges").json()["items"]) == 2

        respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(200, json=CHAT_OK))
        resp = client.post(
            "/api/commands/challenges/run",
            json={"config_id": "demo", "challenge_ids": ["c1"]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["challenge_id"] == "c1"
        items, total = client.app.state.deps.db.list_records(source="challenge")
        assert total == 1


@respx.mock
def test_admin_reload_without_hook_returns_409_with_instructions(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(404))
        resp = client.post("/api/commands/admin/reload", json={"config_id": "demo"})
        assert resp.status_code == 409
        assert "admin_hook" in resp.json()["detail"]


@respx.mock
def test_admin_reload_with_hook_forwards(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(200, json={"admin": True}))
        route = respx.post(f"{BASE}/v1/admin/reload").mock(
            return_value=httpx.Response(200, json={"reloaded": ["demo"]})
        )
        resp = client.post("/api/commands/admin/reload", json={"config_id": "demo"})
        assert resp.status_code == 200
        assert resp.json() == {"reloaded": ["demo"]}
        assert route.called


@respx.mock
def test_challenges_run_isolates_upstream_errors(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/challenges").mock(
            return_value=httpx.Response(200, json=[{"id": "c1", "input": "hack"}, {"id": "c2", "input": "spam"}])
        )
        route = respx.post(f"{BASE}/v1/chat/completions")
        route.side_effect = [
            httpx.ConnectError("refused"),
            httpx.Response(200, json=CHAT_OK),
        ]
        resp = client.post(
            "/api/commands/challenges/run",
            json={"config_id": "demo", "challenge_ids": ["c1", "c2"]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 2
        failed = next(r for r in results if r["challenge_id"] == "c1")
        assert failed["status_code"] == 502
        assert "error" in failed["response"]
        succeeded = next(r for r in results if r["challenge_id"] == "c2")
        assert succeeded["status_code"] == 200
        items, total = client.app.state.deps.db.list_records(source="challenge")
        assert total == 1
