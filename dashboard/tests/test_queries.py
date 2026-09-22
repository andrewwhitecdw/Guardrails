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

from backend.db import Database
from backend.models import RequestRecord
from backend.queries import overview_stats, rails_frequency


def seed(db):
    for i, (status, rail, stop, dur, in_tok, out_tok) in enumerate(
        [
            ("allowed", "codeword", False, 0.1, 10, 5),
            ("blocked", "self check input", True, 0.5, 20, 0),
            ("blocked", "self check input", True, 1.5, 30, 0),
            ("allowed", "codeword", False, 2.5, 5, 5),
        ]
    ):
        db.insert_record(
            RequestRecord(
                id=f"x{i}",
                ts=1000 + i * 1000,
                source="proxy",
                status=status,
                rails=[{"name": rail, "stop": stop}],
                llm_calls=[{"prompt_tokens": in_tok, "completion_tokens": out_tok, "total_tokens": in_tok + out_tok}],
                phase_durations={"total_duration": dur},
            )
        )


def test_overview_stats(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    seed(db)
    stats = overview_stats(db, 0, 10_000)
    assert stats["count"] == 4
    assert stats["blocked"] == 2
    assert stats["errors"] == 0
    assert stats["input_tokens"] == 65
    assert stats["output_tokens"] == 10
    assert stats["p50_ms"] == 1000.0
    assert stats["p95_ms"] == 2500.0
    assert len(stats["buckets"]) > 0
    assert sum(b["count"] for b in stats["buckets"]) == 4
    db.close()


def test_overview_stats_empty(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    stats = overview_stats(db, 0, 10_000)
    assert stats["count"] == 0
    assert stats["p50_ms"] is None
    assert stats["p95_ms"] is None
    db.close()


def test_rails_frequency(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    seed(db)
    rails = rails_frequency(db, 0, 10_000)
    assert rails[0] == {"name": "self check input", "count": 2, "blocked": 2}
    assert rails[1] == {"name": "codeword", "count": 2, "blocked": 0}
    db.close()
