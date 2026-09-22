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
import re
import time
import uuid
from typing import Any

from .models import RequestRecord

_WS_RE = re.compile(r"\s+")


def summarize(text: str, limit: int = 300) -> str:
    collapsed = _WS_RE.sub(" ", text).strip()
    return collapsed[: limit - 1] + "…" if len(collapsed) > limit else collapsed


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return json.dumps(content) if content is not None else ""


def _last_user_message(body: dict[str, Any]) -> str:
    for message in reversed(body.get("messages") or []):
        if message.get("role") == "user":
            return _message_content(message)
    return ""


def _response_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    return _message_content(choices[0].get("message") or {})


def record_from_chat(body: dict[str, Any], data: dict[str, Any], source: str = "proxy") -> RequestRecord:
    guardrails = data.get("guardrails") or {}
    log = guardrails.get("log") or {}

    rails = [
        {
            "type": r.get("type"),
            "name": r.get("name"),
            "stop": bool(r.get("stop")),
            "duration": r.get("duration"),
            "decisions": r.get("decisions") or [],
        }
        for r in (log.get("activated_rails") or [])
    ]
    llm_calls = [
        {
            "task": c.get("task"),
            "provider": c.get("llm_provider_name"),
            "model": c.get("llm_model_name"),
            "prompt_tokens": c.get("prompt_tokens"),
            "completion_tokens": c.get("completion_tokens"),
            "total_tokens": c.get("total_tokens"),
            "duration": c.get("duration"),
            "from_cache": bool(c.get("from_cache", False)),
        }
        for c in (log.get("llm_calls") or [])
    ]
    stats = log.get("stats") or {}
    phases = {
        key: stats.get(key)
        for key in (
            "input_rails_duration",
            "dialog_rails_duration",
            "generation_rails_duration",
            "output_rails_duration",
            "total_duration",
            "llm_calls_duration",
            "llm_calls_count",
        )
        if stats.get(key) is not None
    }

    error_obj = data.get("error")
    if error_obj is not None:
        status = "error"
        error = error_obj.get("message") if isinstance(error_obj, dict) else str(error_obj)
    elif any(r["stop"] for r in rails):
        status = "blocked"
        error = None
    else:
        status = "allowed"
        error = None

    req_guardrails = body.get("guardrails") or {}
    return RequestRecord(
        id=str(uuid.uuid4()),
        ts=int(time.time() * 1000),
        source=source,
        status=status,
        interaction_id=None,
        config_id=req_guardrails.get("config_id"),
        thread_id=req_guardrails.get("thread_id"),
        input_summary=summarize(_last_user_message(body)),
        output_summary=summarize(_response_content(data)),
        rails=rails,
        llm_calls=llm_calls,
        phase_durations=phases,
        error=error,
        raw_request=body,
        raw_response=data,
    )


def record_from_stream(
    body: dict[str, Any],
    sse_text: str,
    started_monotonic: float,
    ended_monotonic: float,
    source: str = "proxy",
) -> RequestRecord:
    """Build a record from a completed SSE stream.

    Streaming responses do not carry the guardrails generation log, so only the
    assembled output text and a client-measured duration are captured.
    """
    content_parts: list[str] = []
    for event in sse_text.split("\n\n"):
        for line in event.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
            if payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for choice in chunk.get("choices") or []:
                delta = (choice.get("delta") or {}).get("content")
                if isinstance(delta, str):
                    content_parts.append(delta)

    req_guardrails = body.get("guardrails") or {}
    return RequestRecord(
        id=str(uuid.uuid4()),
        ts=int(time.time() * 1000),
        source=source,
        status="allowed",
        interaction_id=None,
        config_id=req_guardrails.get("config_id"),
        thread_id=req_guardrails.get("thread_id"),
        input_summary=summarize(_last_user_message(body)),
        output_summary=summarize("".join(content_parts)),
        rails=[],
        llm_calls=[],
        phase_durations={"total_duration": max(0.0, ended_monotonic - started_monotonic)},
        error=None,
        raw_request=body,
        raw_response={"streamed": True, "text": "".join(content_parts)},
    )


def record_from_trace_line(entry: dict[str, Any], ts_ms: int) -> RequestRecord:
    spans = entry.get("spans") or []
    rails: list[dict[str, Any]] = []
    llm_calls: list[dict[str, Any]] = []
    error: str | None = None

    for span in spans:
        attrs = span.get("attributes") or {}
        if span.get("span_type") == "RailSpan":
            rails.append(
                {
                    "type": attrs.get("rail.type"),
                    "name": attrs.get("rail.name"),
                    "stop": bool(attrs.get("rail.stop", False)),
                    "duration": span.get("duration"),
                    "decisions": attrs.get("rail.decisions") or [],
                }
            )
        elif span.get("span_type") == "LLMSpan":
            llm_calls.append(
                {
                    "task": None,
                    "provider": attrs.get("gen_ai.provider.name"),
                    "model": attrs.get("gen_ai.response.model") or attrs.get("gen_ai.request.model"),
                    "prompt_tokens": attrs.get("gen_ai.usage.input_tokens"),
                    "completion_tokens": attrs.get("gen_ai.usage.output_tokens"),
                    "total_tokens": attrs.get("gen_ai.usage.total_tokens"),
                    "duration": span.get("duration"),
                    "from_cache": bool(attrs.get("llm.cache.hit", False)),
                }
            )
        if error is None and span.get("error"):
            err = span["error"]
            error = err.get("message") if isinstance(err, dict) else str(err)
            if not error:
                error = str(err)

    if error is not None:
        status = "error"
    elif any(r["stop"] for r in rails):
        status = "blocked"
    else:
        status = "allowed"

    start_times = [s.get("start_time") for s in spans if s.get("start_time") is not None]
    end_times = [s.get("end_time") for s in spans if s.get("end_time") is not None]
    phases = {}
    if start_times and end_times:
        phases["total_duration"] = max(end_times) - min(start_times)

    return RequestRecord(
        id=str(uuid.uuid4()),
        ts=ts_ms,
        source="trace_file",
        status=status,
        interaction_id=entry.get("trace_id"),
        config_id=None,
        thread_id=None,
        input_summary="",
        output_summary="",
        rails=rails,
        llm_calls=llm_calls,
        phase_durations=phases,
        error=error,
        raw_request=None,
        raw_response=entry,
    )
