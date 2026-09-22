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

from backend.db import Database, RecordWriter
from backend.models import RequestRecord


def make_record(**overrides):
    base = dict(
        id="r1",
        ts=1_000,
        source="proxy",
        status="allowed",
        input_summary="hello",
        output_summary="hi there",
    )
    base.update(overrides)
    return RequestRecord(**base)


def test_insert_and_get_roundtrip(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    rec = make_record(
        rails=[{"type": "input", "name": "self check input", "stop": False, "duration": 0.1}],
        llm_calls=[{"model": "gpt-4", "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}],
        phase_durations={"total_duration": 0.5},
    )
    assert db.insert_record(rec) is True
    got = db.get_record("r1")
    assert got is not None
    assert got.status == "allowed"
    assert got.rails[0]["name"] == "self check input"
    assert got.llm_calls[0]["total_tokens"] == 5
    assert got.phase_durations["total_duration"] == 0.5
    db.close()


def test_trace_dedupe_by_interaction_id(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    first = make_record(id="a", source="trace_file", interaction_id="tid-1")
    second = make_record(id="b", source="trace_file", interaction_id="tid-1")
    assert db.insert_record(first) is True
    assert db.insert_record(second) is False
    assert db.get_record("b") is None
    db.close()


def test_proxy_records_with_same_interaction_id_both_inserted(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    assert db.insert_record(make_record(id="a", interaction_id="x")) is True
    assert db.insert_record(make_record(id="b", interaction_id="x")) is True
    db.close()


def test_list_records_filters_and_pagination(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    for i in range(5):
        db.insert_record(make_record(id=f"r{i}", ts=1000 + i, status="blocked" if i % 2 else "allowed"))
    items, total = db.list_records(status="blocked", limit=10, offset=0)
    assert total == 2
    assert {r.id for r in items} == {"r1", "r3"}
    items, total = db.list_records(limit=2, offset=0)
    assert total == 5 and len(items) == 2
    items, _ = db.list_records(limit=2, offset=4)
    assert [r.id for r in items] == ["r0"]
    db.close()


def test_ingest_state_roundtrip(tmp_path):
    db = Database(str(tmp_path / "d.db"))
    db.set_state("trace:/x.jsonl", "42")
    assert db.get_state("trace:/x.jsonl") == "42"
    db.increment_state("malformed:/x.jsonl")
    db.increment_state("malformed:/x.jsonl")
    assert db.get_state("malformed:/x.jsonl") == "2"
    db.close()


def test_record_writer_serializes_writes(tmp_path):
    async def run():
        db = Database(str(tmp_path / "d.db"))
        writer = RecordWriter(db)
        await writer.start()
        for i in range(10):
            await writer.enqueue(make_record(id=f"w{i}"))
        await writer._queue.join()
        assert writer.written == 10
        await writer.stop()
        db.close()

    import asyncio

    asyncio.run(run())
