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

from backend.main import build_settings, create_app
from backend.settings import Settings
from starlette.testclient import TestClient


def test_build_settings_cli_overrides():
    settings = build_settings(["--guardrails-url", "http://x:1", "--port", "9999", "--db", "/tmp/a.db"])
    assert settings.guardrails_url == "http://x:1"
    assert settings.port == 9999
    assert settings.db_path == "/tmp/a.db"
    defaults = build_settings([])
    assert defaults.port == 8500


def test_create_app_starts_writer_and_tasks(tmp_path):
    settings = Settings(
        guardrails_url="http://guardrails:8000",
        db_path=str(tmp_path / "d.db"),
        trace_globs=[],
        prom_url=None,
    )
    with TestClient(create_app(settings)) as client:
        deps = client.app.state.deps
        assert deps.writer._task is not None
        assert client.get("/api/status").status_code == 200


def test_static_files_served_when_present(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets").mkdir()
    settings = Settings(
        guardrails_url="http://guardrails:8000",
        db_path=str(tmp_path / "d.db"),
        static_dir=str(dist),
    )
    with TestClient(create_app(settings)) as client:
        assert "spa" in client.get("/").text
