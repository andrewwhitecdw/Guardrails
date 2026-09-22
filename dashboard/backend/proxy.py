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
import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .deps import Deps
from .models import RequestRecord
from .normalize import _last_user_message, record_from_chat, record_from_stream, summarize

router = APIRouter(prefix="/proxy")

DEFAULT_LOG_OPTIONS = {"activated_rails": True, "llm_calls": True}


def _inject_log_options(body: dict) -> dict:
    guardrails = body.setdefault("guardrails", {})
    options = guardrails.setdefault("options", {})
    log = options.setdefault("log", {})
    for key, value in DEFAULT_LOG_OPTIONS.items():
        log.setdefault(key, value)
    return body


def _deps(request: Request) -> Deps:
    return request.app.state.deps


@router.post("/v1/chat/completions")
async def proxy_chat_completions(request: Request):
    body = await request.json()
    deps = _deps(request)
    return await forward_chat(deps, body, source="proxy")


@router.post("/v1/checks")
async def proxy_checks(request: Request):
    body = await request.json()
    deps = _deps(request)
    try:
        upstream = await deps.http.post(f"{deps.settings.guardrails_url}/v1/checks", json=body)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="guardrails server unreachable")
    if upstream.status_code != 200:
        return Response(
            upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type")
        )
    try:
        data = upstream.json()
    except json.JSONDecodeError:
        return Response(
            upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type")
        )
    await deps.writer.enqueue(_record_from_check(body, data))
    return JSONResponse(data)


async def forward_chat(deps: Deps, body: dict, source: str) -> Response:
    """Forward a chat completion to the guardrails server and record it.

    Shared by the /proxy route and the console/challenge commands.
    """
    body = _inject_log_options(body)
    if body.get("stream"):
        return await _forward_streaming(deps, body, source=source)
    return await _forward_chat(deps, body, source=source)


async def _forward_chat(deps: Deps, body: dict, source: str) -> Response:
    try:
        upstream = await deps.http.post(f"{deps.settings.guardrails_url}/v1/chat/completions", json=body)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="guardrails server unreachable")
    media_type = upstream.headers.get("content-type", "application/json")
    try:
        data = upstream.json()
    except (json.JSONDecodeError, ValueError):
        return Response(upstream.content, status_code=upstream.status_code, media_type=media_type)
    if upstream.status_code == 200:
        await deps.writer.enqueue(record_from_chat(body, data, source=source))
    return JSONResponse(data, status_code=upstream.status_code)


async def _forward_streaming(deps: Deps, body: dict, source: str = "proxy") -> StreamingResponse:
    url = f"{deps.settings.guardrails_url}/v1/chat/completions"
    started = time.monotonic()

    async def event_gen():
        buffer: list[bytes] = []
        try:
            async with deps.http.stream("POST", url, json=body) as upstream:
                if upstream.status_code != 200:
                    yield await upstream.aread()
                    return
                async for chunk in upstream.aiter_raw():
                    buffer.append(chunk)
                    yield chunk
        except httpx.HTTPError as exc:
            yield json.dumps({"error": {"message": str(exc)}}).encode()
            return
        ended = time.monotonic()
        text = b"".join(buffer).decode(errors="replace")
        if buffer:
            await deps.writer.enqueue(record_from_stream(body, text, started, ended, source=source))

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _record_from_check(body: dict, data: dict) -> RequestRecord:
    rail_name = data.get("rail")
    status = data.get("status")
    record_status = status if status in ("allowed", "blocked") else "allowed"
    return RequestRecord(
        id=uuid.uuid4().hex,
        ts=int(time.time() * 1000),
        source="check",
        status=record_status,
        config_id=body.get("config_id"),
        input_summary=summarize(_last_user_message(body)),
        output_summary=summarize(str(data.get("content") or "")),
        rails=[{"name": rail_name, "stop": record_status == "blocked"}] if rail_name else [],
        raw_request=body,
        raw_response=data,
    )
