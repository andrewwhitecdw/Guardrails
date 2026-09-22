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

import asyncio
import json
import sqlite3
import threading
from pathlib import Path

from .models import RequestRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS request_records (
  id TEXT PRIMARY KEY,
  ts INTEGER NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  interaction_id TEXT,
  config_id TEXT,
  thread_id TEXT,
  input_summary TEXT,
  output_summary TEXT,
  rails_json TEXT,
  llm_calls_json TEXT,
  phase_durations_json TEXT,
  error TEXT,
  raw_request_json TEXT,
  raw_response_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_records_ts ON request_records(ts);
CREATE INDEX IF NOT EXISTS idx_records_status ON request_records(status);
CREATE INDEX IF NOT EXISTS idx_records_source ON request_records(source);
CREATE INDEX IF NOT EXISTS idx_records_interaction ON request_records(interaction_id);

CREATE TABLE IF NOT EXISTS metric_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  labels_json TEXT NOT NULL,
  ts INTEGER NOT NULL,
  value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_name_ts ON metric_samples(name, ts);

CREATE TABLE IF NOT EXISTS ingest_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

INSERT_SQL = """
INSERT INTO request_records
  (id, ts, source, status, interaction_id, config_id, thread_id,
   input_summary, output_summary, rails_json, llm_calls_json,
   phase_durations_json, error, raw_request_json, raw_response_json)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


class Database:
    def __init__(self, path: str):
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(target), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # -- request records ----------------------------------------------------

    def insert_record(self, rec: RequestRecord) -> bool:
        """Insert a record. Returns False if skipped as a duplicate."""
        if rec.interaction_id and rec.source == "trace_file":
            existing = self.query(
                "SELECT 1 FROM request_records WHERE interaction_id = ? LIMIT 1",
                (rec.interaction_id,),
            )
            if existing:
                return False
        self.execute(
            INSERT_SQL,
            (
                rec.id,
                rec.ts,
                rec.source,
                rec.status,
                rec.interaction_id,
                rec.config_id,
                rec.thread_id,
                rec.input_summary,
                rec.output_summary,
                json.dumps(rec.rails),
                json.dumps(rec.llm_calls),
                json.dumps(rec.phase_durations),
                rec.error,
                json.dumps(rec.raw_request) if rec.raw_request is not None else None,
                json.dumps(rec.raw_response) if rec.raw_response is not None else None,
            ),
        )
        return True

    def get_record(self, record_id: str) -> RequestRecord | None:
        rows = self.query("SELECT * FROM request_records WHERE id = ?", (record_id,))
        return RequestRecord.from_row(rows[0]) if rows else None

    def list_records(
        self,
        start_ts: int | None = None,
        end_ts: int | None = None,
        status: str | None = None,
        source: str | None = None,
        config_id: str | None = None,
        rail: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list, int]:
        where, params = [], []
        if start_ts is not None:
            where.append("ts >= ?")
            params.append(start_ts)
        if end_ts is not None:
            where.append("ts <= ?")
            params.append(end_ts)
        if status:
            where.append("status = ?")
            params.append(status)
        if source:
            where.append("source = ?")
            params.append(source)
        if config_id:
            where.append("config_id = ?")
            params.append(config_id)
        if rail:
            where.append("rails_json LIKE ?")
            params.append('%"name": ' + json.dumps(rail) + "%")
        if search:
            where.append("(input_summary LIKE ? OR output_summary LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.query(f"SELECT COUNT(*) AS c FROM request_records{clause}", tuple(params))[0]["c"]
        rows = self.query(
            f"SELECT * FROM request_records{clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
            tuple(params) + (limit, offset),
        )
        return [RequestRecord.from_row(r) for r in rows], total

    # -- metric samples -----------------------------------------------------

    def insert_samples(self, samples: list[tuple[str, str, int, float]]):
        if not samples:
            return
        self._conn_executemany(
            "INSERT INTO metric_samples (name, labels_json, ts, value) VALUES (?,?,?,?)",
            samples,
        )

    def _conn_executemany(self, sql: str, rows: list[tuple]):
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def metric_series(self, name_prefix: str, start_ts: int, end_ts: int, limit: int = 5000) -> list[dict]:
        rows = self.query(
            "SELECT name, labels_json, ts, value FROM metric_samples"
            " WHERE name LIKE ? AND ts >= ? AND ts <= ? ORDER BY ts ASC LIMIT ?",
            (name_prefix + "%", start_ts, end_ts, limit),
        )
        return [
            {"name": r["name"], "labels": json.loads(r["labels_json"]), "ts": r["ts"], "value": r["value"]}
            for r in rows
        ]

    def metric_names(self) -> list[str]:
        rows = self.query("SELECT DISTINCT name FROM metric_samples ORDER BY name")
        return [r["name"] for r in rows]

    # -- ingestion state ----------------------------------------------------

    def get_state(self, key: str, default: str | None = None) -> str | None:
        rows = self.query("SELECT value FROM ingest_state WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_state(self, key: str, value: str):
        self.execute(
            "INSERT INTO ingest_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def increment_state(self, key: str, amount: int = 1):
        current = self.get_state(key)
        self.set_state(key, str((int(current) if current is not None else 0) + amount))


class RecordWriter:
    """Serializes record writes through an asyncio queue (single writer)."""

    def __init__(self, db: Database):
        self._db = db
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self.written = 0
        self.dropped = 0

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def enqueue(self, rec: RequestRecord):
        await self._queue.put(rec)

    async def drain(self):
        """Wait until all enqueued records have been written."""
        await self._queue.join()

    async def _run(self):
        while True:
            rec = await self._queue.get()
            try:
                if self._db.insert_record(rec):
                    self.written += 1
                else:
                    self.dropped += 1
            finally:
                self._queue.task_done()

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
