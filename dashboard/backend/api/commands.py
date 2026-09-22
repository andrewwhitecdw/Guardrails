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
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from ..proxy import _record_from_check, forward_chat

router = APIRouter(prefix="/api/commands")

RELOAD_INSTRUCTIONS = (
    "The guardrails server does not have the admin hook installed. "
    "Copy dashboard/admin_hook/guardrails_admin.py into your guardrails config "
    "folder and call its init(app) from the folder's config.py init(app)."
)


@router.post("/console/run")
async def console_run(request: Request):
    """Run a test prompt through the recording pipeline (source=console)."""
    deps = request.app.state.deps
    body = await request.json()
    chat_body: dict = {"messages": body.get("messages") or []}
    if body.get("config_id"):
        chat_body["guardrails"] = {"config_id": body["config_id"]}
        if body.get("thread_id"):
            chat_body["guardrails"]["thread_id"] = body["thread_id"]
        if body.get("context"):
            chat_body["guardrails"]["context"] = body["context"]
    if body.get("stream"):
        chat_body["stream"] = True
    return await forward_chat(deps, chat_body, source="console")


@router.post("/checks/run")
async def checks_run(request: Request):
    deps = request.app.state.deps
    body = await request.json()
    payload: dict = {"messages": body.get("messages") or []}
    if body.get("config_id"):
        payload["config_id"] = body["config_id"]
    if body.get("rail_types"):
        payload["rail_types"] = body["rail_types"]

    try:
        upstream = await deps.http.post(f"{deps.settings.guardrails_url}/v1/checks", json=payload)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="guardrails server unreachable")
    if upstream.status_code == 200:
        try:
            data = upstream.json()
        except json.JSONDecodeError:
            data = None
        if data is not None:
            await deps.writer.enqueue(_record_from_check(payload, data))
            await deps.writer.drain()
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


@router.get("/challenges")
async def list_challenges(request: Request):
    deps = request.app.state.deps
    items = await deps.client.challenges()
    if items is None:
        raise HTTPException(status_code=502, detail="guardrails server unreachable")
    return {"items": items}


@router.post("/challenges/run")
async def run_challenges(request: Request):
    """Run selected challenges against a config; results recorded (source=challenge)."""
    deps = request.app.state.deps
    body = await request.json()
    challenges = await deps.client.challenges()
    if challenges is None:
        raise HTTPException(status_code=502, detail="guardrails server unreachable")
    selected_ids = body.get("challenge_ids")
    selected = [c for c in challenges if not selected_ids or c.get("id") in selected_ids]
    if not selected:
        raise HTTPException(status_code=404, detail="no matching challenges")

    config_id = body.get("config_id")
    results = []
    for challenge in selected:
        prompt = challenge.get("input") or challenge.get("prompt") or ""
        chat_body: dict = {"messages": [{"role": "user", "content": prompt}]}
        if config_id:
            chat_body["guardrails"] = {"config_id": config_id}
        response = await forward_chat(deps, chat_body, source="challenge")
        content = b""
        if hasattr(response, "body"):
            content = response.body
        try:
            data = json.loads(content) if content else {}
        except json.JSONDecodeError:
            data = {}
        results.append(
            {
                "challenge_id": challenge.get("id"),
                "challenge": challenge,
                "status_code": getattr(response, "status_code", 500),
                "response": data,
            }
        )
    return {"results": results}


@router.get("/admin/capabilities")
async def admin_capabilities(request: Request):
    deps = request.app.state.deps
    return {"installed": (await deps.client.admin_capabilities()) is not None}


@router.post("/admin/reload")
async def admin_reload(request: Request):
    deps = request.app.state.deps
    body = await request.json()
    if (await deps.client.admin_capabilities()) is None:
        raise HTTPException(status_code=409, detail=RELOAD_INSTRUCTIONS)
    result = await deps.client.admin_reload(body.get("config_id"))
    if result is None:
        raise HTTPException(status_code=502, detail="reload failed or server unreachable")
    return result
