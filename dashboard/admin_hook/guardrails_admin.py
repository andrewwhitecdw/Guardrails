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

"""Admin endpoints for the Guardrails Admin Dashboard.

Drop this file into your guardrails config folder (the folder passed to
`nemoguardrails server --config` that contains your per-bot subfolders) and
wire it from the folder's config.py:

    import importlib.util
    import os

    def _load_admin_hook(app):
        path = os.path.join(os.path.dirname(__file__), "guardrails_admin.py")
        spec = importlib.util.spec_from_file_location("guardrails_admin", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.init(app)

    def init(app):
        _load_admin_hook(app)

The hook is only loaded by the server when the config root is not in
single-config mode (see nemoguardrails/server/api.py).
"""

from pydantic import BaseModel


class _ReloadRequest(BaseModel):
    config_id: str | None = None


def init(app):
    from nemoguardrails.server import api as server_api

    @app.get("/v1/admin/capabilities")
    async def admin_capabilities():
        return {"admin": True, "reload": True}

    @app.post("/v1/admin/reload")
    async def admin_reload(request: _ReloadRequest | None = None):
        """Drop cached LLMRails instances so configs rebuild on next request.

        Mirrors the built-in auto-reload behavior, but also matches merged
        config keys ("id1-id2") and model-suffixed keys ("id:model").
        """
        config_id = request.config_id if request else None
        reloaded = []
        for key in list(server_api.llm_rails_instances.keys()):
            # A config id containing "-" is split into fragments, so reloading
            # "bot" also matches a cached key "my-bot" — inherent to the
            # server's own cache-key format; acceptable for a local admin tool.
            ids = key.split(":")[0].split("-")
            if config_id is None or config_id in ids:
                instance = server_api.llm_rails_instances.pop(key)
                reloaded.append(key)
                if instance is not None and hasattr(instance, "events_history_cache"):
                    server_api.llm_rails_events_history_cache[key] = instance.events_history_cache
        return {"reloaded": reloaded}
