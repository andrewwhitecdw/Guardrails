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
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RequestRecord:
    id: str
    ts: int  # epoch milliseconds
    source: str  # proxy | trace_file | challenge | console | check
    status: str = "allowed"  # allowed | blocked | error
    interaction_id: str | None = None
    config_id: str | None = None
    thread_id: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    rails: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    phase_durations: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    raw_request: dict[str, Any] | None = None
    raw_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_row(row) -> "RequestRecord":
        return RequestRecord(
            id=row["id"],
            ts=row["ts"],
            source=row["source"],
            status=row["status"],
            interaction_id=row["interaction_id"],
            config_id=row["config_id"],
            thread_id=row["thread_id"],
            input_summary=row["input_summary"] or "",
            output_summary=row["output_summary"] or "",
            rails=json.loads(row["rails_json"] or "[]"),
            llm_calls=json.loads(row["llm_calls_json"] or "[]"),
            phase_durations=json.loads(row["phase_durations_json"] or "{}"),
            error=row["error"],
            raw_request=json.loads(row["raw_request_json"]) if row["raw_request_json"] else None,
            raw_response=json.loads(row["raw_response_json"]) if row["raw_response_json"] else None,
        )
