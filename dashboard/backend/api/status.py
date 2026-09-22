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

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/status")
async def get_status(request: Request):
    deps = request.app.state.deps
    health = await deps.client.health()
    configs = await deps.client.configs()
    models = await deps.client.models()
    capabilities = await deps.client.admin_capabilities()

    malformed = {}
    for row in deps.db.query("SELECT key, value FROM ingest_state WHERE key LIKE 'malformed:%'"):
        malformed[row["key"][len("malformed:") :]] = int(row["value"])

    return {
        "guardrails": {
            "url": deps.settings.guardrails_url,
            "healthy": health is not None,
            "configs": configs,
            "models": models,
        },
        "ingestion": {
            "trace_globs": deps.settings.trace_globs,
            "prom_url": deps.settings.prom_url,
            "malformed": malformed,
            "records_written": deps.writer.written,
            "records_dropped_duplicates": deps.writer.dropped,
        },
        "admin_hook": capabilities is not None,
    }
