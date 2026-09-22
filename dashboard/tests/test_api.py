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
