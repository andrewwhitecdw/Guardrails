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

from backend.db import Database, RecordWriter
from backend.ingest import TraceIngester

TRACE_LINE = {
    "schema_version": "2.0",
    "trace_id": "t-1",
    "spans": [
        {
            "name": "interaction",
            "span_type": "InteractionSpan",
            "duration": 1.0,
            "start_time": 0.0,
            "end_time": 1.0,
            "attributes": {},
        },
        {
            "name": "self check input",
            "span_type": "RailSpan",
            "duration": 0.2,
            "start_time": 0.0,
            "end_time": 0.2,
            "attributes": {"rail.type": "input", "rail.name": "self check input", "rail.stop": True},
        },
    ],
}


async def make_ingester(tmp_path, globs):
    db = Database(str(tmp_path / "d.db"))
    writer = RecordWriter(db)
    await writer.start()
    ingester = TraceIngester(db, writer, globs)
    return db, writer, ingester


async def test_ingests_new_trace_lines_and_tracks_offset(tmp_path):
    trace = tmp_path / "traces" / "trace.jsonl"
    trace.parent.mkdir()
    trace.write_text(json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "traces" / "*.jsonl")])

    await ingester.scan_once()
    await writer._queue.join()

    items, total = db.list_records(source="trace_file")
    assert total == 1
    assert items[0].interaction_id == "t-1"
    assert items[0].status == "blocked"
    assert db.get_state(f"trace:{trace}") is not None

    # second scan with no new data inserts nothing
    await ingester.scan_once()
    await writer._queue.join()
    _, total = db.list_records(source="trace_file")
    assert total == 1

    # appended line is picked up, and a duplicate interaction id is skipped
    with trace.open("a") as f:
        f.write(json.dumps(TRACE_LINE) + "\n")
        other = dict(TRACE_LINE, trace_id="t-2")
        f.write(json.dumps(other) + "\n")
    await ingester.scan_once()
    await writer._queue.join()
    _, total = db.list_records(source="trace_file")
    assert total == 2

    await writer.stop()
    db.close()


async def test_malformed_lines_are_counted_and_skipped(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("not json\n" + json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])

    await ingester.scan_once()
    await writer._queue.join()

    assert db.get_state(f"malformed:{trace}") == "1"
    _, total = db.list_records(source="trace_file")
    assert total == 1
    await writer.stop()
    db.close()


async def test_truncated_file_resets_offset(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])
    await ingester.scan_once()
    await writer._queue.join()

    # simulate rotation: file shrinks back to zero and gets new content
    trace.write_text(json.dumps(dict(TRACE_LINE, trace_id="t-9")) + "\n")
    await ingester.scan_once()
    await writer._queue.join()

    _, total = db.list_records(source="trace_file")
    assert total == 2
    await writer.stop()
    db.close()
