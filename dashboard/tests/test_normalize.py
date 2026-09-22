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

from backend.normalize import record_from_chat, record_from_stream, record_from_trace_line

CHAT_RESPONSE = {
    "id": "chatcmpl-1",
    "choices": [{"message": {"role": "assistant", "content": "I cannot help with that."}, "finish_reason": "stop"}],
    "guardrails": {
        "config_id": "demo",
        "log": {
            "activated_rails": [
                {
                    "type": "input",
                    "name": "self check input",
                    "decisions": [],
                    "stop": True,
                    "started_at": 1.0,
                    "finished_at": 1.2,
                    "duration": 0.2,
                },
            ],
            "stats": {
                "input_rails_duration": 0.2,
                "dialog_rails_duration": None,
                "generation_rails_duration": None,
                "output_rails_duration": None,
                "total_duration": 1.5,
                "llm_calls_duration": 0.9,
                "llm_calls_count": 1,
            },
            "llm_calls": [
                {
                    "task": "self check",
                    "duration": 0.9,
                    "prompt_tokens": 42,
                    "completion_tokens": 7,
                    "total_tokens": 49,
                    "started_at": 1.1,
                    "finished_at": 2.0,
                    "llm_model_name": "gpt-4",
                    "llm_provider_name": "openai",
                    "from_cache": False,
                },
            ],
        },
    },
}

CHAT_BODY = {
    "messages": [{"role": "user", "content": "how do I hack a wifi password?"}],
    "guardrails": {"config_id": "demo"},
}


def test_record_from_chat_blocked():
    rec = record_from_chat(CHAT_BODY, CHAT_RESPONSE)
    assert rec.source == "proxy"
    assert rec.status == "blocked"
    assert rec.config_id == "demo"
    assert rec.rails[0]["name"] == "self check input"
    assert rec.rails[0]["stop"] is True
    assert rec.phase_durations["total_duration"] == 1.5
    assert rec.llm_calls[0]["model"] == "gpt-4"
    assert rec.llm_calls[0]["total_tokens"] == 49
    assert "wifi" in rec.input_summary
    assert rec.output_summary == "I cannot help with that."
    assert rec.raw_response == CHAT_RESPONSE


def test_record_from_chat_allowed_when_no_stop():
    import copy

    data = copy.deepcopy(CHAT_RESPONSE)
    data["guardrails"]["log"]["activated_rails"][0]["stop"] = False
    data["choices"][0]["message"]["content"] = "Sure!"
    rec = record_from_chat(CHAT_BODY, data)
    assert rec.status == "allowed"


def test_record_from_chat_error_status():
    data = {"error": {"message": "boom", "type": "server_error"}}
    rec = record_from_chat(CHAT_BODY, data)
    assert rec.status == "error"
    assert rec.error == "boom"


def test_record_from_chat_without_log_options():
    data = {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
    rec = record_from_chat(CHAT_BODY, data)
    assert rec.status == "allowed"
    assert rec.rails == []
    assert rec.llm_calls == []


def test_record_from_stream():
    chunk = {"choices": [{"delta": {"content": "Hello"}, "index": 0}]}
    sse = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
    rec = record_from_stream(CHAT_BODY, sse, started_monotonic=100.0, ended_monotonic=101.25)
    assert rec.source == "proxy"
    assert rec.status == "allowed"
    assert rec.output_summary == "Hello"
    assert rec.phase_durations["total_duration"] == 1.25
    assert rec.rails == []


TRACE_LINE = {
    "schema_version": "2.0",
    "trace_id": "abc-123",
    "spans": [
        {
            "name": "interaction",
            "span_type": "InteractionSpan",
            "duration": 2.0,
            "start_time": 0.0,
            "end_time": 2.0,
            "attributes": {"span.kind": "server", "gen_ai.operation.name": "chat"},
        },
        {
            "name": "self check input",
            "span_type": "RailSpan",
            "duration": 0.3,
            "start_time": 0.0,
            "end_time": 0.3,
            "attributes": {"rail.type": "input", "rail.name": "self check input", "rail.stop": True},
        },
        {
            "name": "generate bot message",
            "span_type": "LLMSpan",
            "duration": 1.0,
            "start_time": 0.5,
            "end_time": 1.5,
            "attributes": {
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": "gpt-4",
                "gen_ai.response.model": "gpt-4",
                "gen_ai.usage.input_tokens": 10,
                "gen_ai.usage.output_tokens": 5,
                "gen_ai.usage.total_tokens": 15,
                "llm.cache.hit": False,
            },
        },
    ],
}


def test_record_from_trace_line():
    rec = record_from_trace_line(TRACE_LINE, ts_ms=999_000)
    assert rec.source == "trace_file"
    assert rec.interaction_id == "abc-123"
    assert rec.ts == 999_000
    assert rec.status == "blocked"
    assert rec.rails[0]["name"] == "self check input"
    assert rec.llm_calls[0]["model"] == "gpt-4"
    assert rec.llm_calls[0]["prompt_tokens"] == 10
    assert rec.phase_durations["total_duration"] == 2.0


def test_record_from_trace_line_error_span():
    import copy

    line = copy.deepcopy(TRACE_LINE)
    line["spans"][1]["error"] = {"occurred": True, "type": "ValueError", "message": "bad rail"}
    rec = record_from_trace_line(line, ts_ms=0)
    assert rec.status == "error"
    assert rec.error == "bad rail"


def test_record_from_trace_line_string_error():
    import copy

    line = copy.deepcopy(TRACE_LINE)
    line["spans"][1]["error"] = "boom"
    rec = record_from_trace_line(line, ts_ms=0)
    assert rec.status == "error"
    assert rec.error == "boom"


def test_record_from_trace_line_absolute_times():
    import copy

    line = copy.deepcopy(TRACE_LINE)
    for span in line["spans"]:
        span["start_time"] = span["start_time"] + 1000.0
        span["end_time"] = span["end_time"] + 1000.0
    rec = record_from_trace_line(line, ts_ms=0)
    assert rec.phase_durations["total_duration"] == 2.0
