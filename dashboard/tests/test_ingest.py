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
import os
import time

import httpx
import respx
from backend.db import Database, RecordWriter
from backend.ingest import TraceIngester, parse_prometheus_text, scrape_prometheus_once

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
    await writer.drain()

    items, total = db.list_records(source="trace_file")
    assert total == 1
    assert items[0].interaction_id == "t-1"
    assert items[0].status == "blocked"
    assert db.get_state(f"trace:{trace}") is not None

    # second scan with no new data inserts nothing
    await ingester.scan_once()
    await writer.drain()
    _, total = db.list_records(source="trace_file")
    assert total == 1

    # appended line is picked up, and a duplicate interaction id is skipped
    with trace.open("a") as f:
        f.write(json.dumps(TRACE_LINE) + "\n")
        other = dict(TRACE_LINE, trace_id="t-2")
        f.write(json.dumps(other) + "\n")
    await ingester.scan_once()
    await writer.drain()
    _, total = db.list_records(source="trace_file")
    assert total == 2

    await writer.stop()
    db.close()


async def test_malformed_lines_are_counted_and_skipped(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("not json\n" + json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])

    await ingester.scan_once()
    await writer.drain()

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
    await writer.drain()

    # simulate rotation: file shrinks back to zero and gets new content
    trace.write_text(json.dumps(dict(TRACE_LINE, trace_id="t-9")) + "\n")
    await ingester.scan_once()
    await writer.drain()

    _, total = db.list_records(source="trace_file")
    assert total == 2
    await writer.stop()
    db.close()


async def test_non_dict_json_lines_are_counted_malformed(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("42\n" + '"hi"\n' + "[1]\n" + json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])

    await ingester.scan_once()
    await writer.drain()

    assert db.get_state(f"malformed:{trace}") == "3"
    _, total = db.list_records(source="trace_file")
    assert total == 1
    await writer.stop()
    db.close()


async def test_malformed_record_shape_is_skipped_and_counted(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({"spans": [42]}) + "\n" + json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])

    await ingester.scan_once()
    await writer.drain()

    assert db.get_state(f"malformed:{trace}") == "1"
    _, total = db.list_records(source="trace_file")
    assert total == 1
    await writer.stop()
    db.close()


async def test_partial_last_line_is_held_back_until_complete(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps(TRACE_LINE) + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])

    await ingester.scan_once()
    await writer.drain()
    _, total = db.list_records(source="trace_file")
    assert total == 1

    # a concurrent writer flushed a line without its trailing newline
    line2 = json.dumps(dict(TRACE_LINE, trace_id="t-2"))
    with trace.open("a") as f:
        f.write(line2[:-1])
    await ingester.scan_once()
    await writer.drain()

    # the partial fragment is held back, not counted malformed and not lost
    assert db.get_state(f"malformed:{trace}") is None
    _, total = db.list_records(source="trace_file")
    assert total == 1

    # the remainder of the line lands; it is ingested whole on the next scan
    with trace.open("a") as f:
        f.write(line2[-1] + "\n")
    await ingester.scan_once()
    await writer.drain()

    assert db.get_state(f"malformed:{trace}") is None
    _, total = db.list_records(source="trace_file")
    assert total == 2
    await writer.stop()
    db.close()


async def test_equal_size_rewrite_with_fresh_mtime_is_reingested(tmp_path):
    trace = tmp_path / "trace.jsonl"
    line1 = json.dumps(TRACE_LINE)
    trace.write_text(line1 + "\n")
    db, writer, ingester = await make_ingester(tmp_path, [str(tmp_path / "*.jsonl")])
    await ingester.scan_once()
    await writer.drain()

    # rewrite in place (no truncation) with an equal-length trace_id
    line2 = json.dumps(dict(TRACE_LINE, trace_id="t-X"))
    assert len(line2) == len(line1)
    with trace.open("r+") as f:
        f.seek(0)
        f.write(line2 + "\n")
    os.utime(trace, ns=(time.time_ns(), time.time_ns()))

    await ingester.scan_once()
    await writer.drain()

    _, total = db.list_records(source="trace_file")
    assert total == 2
    await writer.stop()
    db.close()


PROM_TEXT = """# HELP guardrails_nonstream_queued Pending non-streaming requests.
# TYPE guardrails_nonstream_queued gauge
guardrails_nonstream_queued 3
# TYPE guardrails_nonstream_active gauge
guardrails_nonstream_active 2
# TYPE guardrails_nonstream_rejections counter
guardrails_nonstream_rejections_total 7
http_requests_total{handler="/v1/chat/completions",code="200"} 42.5
"""


def test_parse_prometheus_text():
    samples = parse_prometheus_text(PROM_TEXT)
    by_name = {}
    for name, labels, value in samples:
        by_name.setdefault(name, []).append((labels, value))
    assert by_name["guardrails_nonstream_queued"] == [({}, 3.0)]
    assert by_name["guardrails_nonstream_active"] == [({}, 2.0)]
    assert by_name["guardrails_nonstream_rejections_total"] == [({}, 7.0)]
    assert by_name["http_requests_total"] == [({"handler": "/v1/chat/completions", "code": "200"}, 42.5)]


def test_parse_skips_comments_and_empty_lines():
    assert parse_prometheus_text("# comment\n\n   \nmetric_a 1\n") == [("metric_a", {}, 1.0)]


@respx.mock
async def test_scrape_prometheus_once(tmp_path):
    respx.get("http://guardrails:9464/metrics").mock(return_value=httpx.Response(200, text=PROM_TEXT))
    db = Database(str(tmp_path / "d.db"))
    http = httpx.AsyncClient()
    await scrape_prometheus_once(db, http, "http://guardrails:9464/metrics")
    names = db.metric_names()
    assert "guardrails_nonstream_queued" in names
    assert "guardrails_nonstream_rejections_total" in names
    series = db.metric_series("guardrails_nonstream", 0, 9_999_999_999_999)
    assert len(series) == 3
    await http.aclose()
    db.close()


@respx.mock
async def test_scrape_failure_is_silent(tmp_path):
    respx.get("http://guardrails:9464/metrics").mock(side_effect=httpx.ConnectError("refused"))
    db = Database(str(tmp_path / "d.db"))
    http = httpx.AsyncClient()
    await scrape_prometheus_once(db, http, "http://guardrails:9464/metrics")
    assert db.metric_names() == []
    await http.aclose()
    db.close()
