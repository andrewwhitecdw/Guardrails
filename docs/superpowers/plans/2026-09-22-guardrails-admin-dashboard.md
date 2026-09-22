# Guardrails Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone local web dashboard (FastAPI + React SPA) that records per-request guardrails data via a recording proxy and file/metrics ingestion, displays it, and issues API commands to a running guardrails server.

**Architecture:** Single `dashboard/` uv project. A FastAPI backend owns a sqlite WAL database, a recording proxy in front of the guardrails server's `/v1/chat/completions` and `/v1/checks`, background ingestion of trace JSONL files and Prometheus scrapes, and a JSON API under `/api`. A Vite React SPA (served from `backend/main.py` as static files) is the UI. An optional drop-in `admin_hook/guardrails_admin.py` adds reload endpoints to the guardrails server via its `config.py init(app)` mechanism.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, httpx, pydantic-settings, stdlib sqlite3; pytest, pytest-asyncio, respx; React 18, TypeScript, Vite, react-router-dom, recharts, vitest.

**Spec:** `docs/superpowers/specs/2026-09-22-guardrails-admin-dashboard-design.md` (committed at `8a008679e`).

**Spec clarifications made in this plan (deliberate, minor):**

1. `request_records.source` enum is extended to `proxy` | `trace_file` | `challenge` | `console` | `check` so console and checks runs recorded through the proxy are distinguishable.
2. Streaming responses from the guardrails server do not include the generation log, so streaming records store the assembled output text and a client-measured total duration only (`status` is `allowed` unless the upstream errored).
3. Trace JSONL lines carry no wall-clock timestamp, so trace-ingested records use the trace file's mtime as `ts`.
4. The admin hook matches cache keys by splitting on `":"` and `"-"` so merged configs (`id1-id2`) and model-suffixed keys (`id:model`) reload too.
5. Background collectors retry on a fixed interval (5 s for traces, `--scrape-interval` for Prometheus) rather than exponential backoff; the guardrails server is expected to be local, so reconnecting promptly matters more than backing off.

**Key schema facts this plan relies on (verified against source):**

- Generation-log request opt-in: `guardrails.options.log.activated_rails` / `llm_calls` booleans (`nemoguardrails/rails/llm/options.py:105-124`).
- Response `guardrails.log` keys: `activated_rails[]` (`type`, `name`, `decisions`, `stop`, `started_at`, `finished_at`, `duration`), `stats` (`input_rails_duration`, `dialog_rails_duration`, `generation_rails_duration`, `output_rails_duration`, `total_duration`, `llm_calls_duration`, `llm_calls_count`, `llm_calls_total_prompt_tokens`, `llm_calls_total_completion_tokens`, `llm_calls_total_tokens`), `llm_calls[]` (`task`, `duration`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `started_at`, `finished_at`, `llm_model_name`, `llm_provider_name`, `from_cache`) (`options.py:219-309`, `nemoguardrails/logging/explain.py`).
- Trace JSONL line: `{"schema_version": "2.0", "trace_id": str, "spans": [...]}`; each span has `span_type` (`InteractionSpan`/`RailSpan`/`ActionSpan`/`LLMSpan`), `duration`, `attributes`; RailSpan attributes use keys `rail.type`, `rail.name`, `rail.stop`, `rail.decisions`; LLMSpan attributes use `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens`, `llm.cache.hit` (`nemoguardrails/tracing/span_formatting.py:44-82`, `tracing/spans.py`).
- Usage stats JSONL lines: aliased keys `nemoSource`, `sessionId`, `event` (`startup`|`heartbeat`), `timestamp`, `nemoguardrailsVersion`, `railTypesInUse`, `numRailsConfigured`, `llmProviders`, `deploymentType`, `railsEngine`, `tracingEnabled`, `streamingConfigured`, `hasKnowledgeBase`, `numCustomFlows`, `builtinFeatures`, `pythonVersion`, `platform`, `osName`, `colangVersion` (`nemoguardrails/telemetry.py:226-343`, written via `model_dump(by_alias=True)` at telemetry.py:802).
- Prometheus exporter only exports `guardrails.nonstream.queued`, `guardrails.nonstream.active`, `guardrails.nonstream.rejections` (`nemoguardrails/server/metrics.py:68`), on a separate listener (default port 9464).
- Server `config.py` hook: file at `<config_root>/config.py` is exec'd; if it defines `init(app)`, it is called with the FastAPI app instance (`nemoguardrails/server/api.py:164-189`). Reload cache: `nemoguardrails.server.api.llm_rails_instances: dict[str, LLMRails]`, keys are `"id1-id2"` plus optional `":model"` suffix (`api.py:355,369-374`).
- `thread_id` on `/v1/chat/completions` without a registered datastore is a hard 400 (`api.py:715-721`).

---

## File Structure

```
dashboard/
├── pyproject.toml
├── README.md
├── backend/
│   ├── __init__.py
│   ├── main.py               # app factory, argparse, lifespan, static mount
│   ├── settings.py           # Settings (pydantic-settings)
│   ├── deps.py               # Deps dataclass (settings, db, writer, http, client)
│   ├── models.py             # RequestRecord dataclass + row mapping
│   ├── db.py                 # Database (sqlite), RecordWriter (asyncio queue)
│   ├── normalize.py          # RequestRecord builders from chat response / SSE / trace line
│   ├── queries.py            # list_records, overview_stats, rails_frequency (thin wrappers)
│   ├── guardrails_client.py  # typed client for the guardrails server
│   ├── proxy.py              # recording proxy + forward_chat used by commands
│   ├── ingest.py             # trace tailing + prometheus scrape loops
│   ├── telemetry.py          # usage stats reader
│   └── api/
│       ├── __init__.py
│       ├── status.py
│       ├── requests.py
│       ├── metrics.py
│       ├── telemetry.py
│       └── commands.py
├── admin_hook/
│   └── guardrails_admin.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_db.py
│   ├── test_normalize.py
│   ├── test_guardrails_client.py
│   ├── test_proxy.py
│   ├── test_ingest.py
│   ├── test_telemetry.py
│   └── test_api.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api.ts
        ├── types.ts
        ├── components.tsx
        └── pages/
            ├── OverviewPage.tsx
            ├── RequestsPage.tsx
            ├── RequestDetail.tsx
            ├── MetricsPage.tsx
            ├── TelemetryPage.tsx
            ├── ConsolePage.tsx
            ├── ChallengesPage.tsx
            └── AdminPage.tsx
```

`queries.py` is split out of `db.py` (not shown as a separate file in the spec's tree) to keep `db.py` focused on storage; same responsibility boundary.

---

### Task 1: Scaffold the dashboard uv project and settings

**Files:**
- Create: `dashboard/pyproject.toml`
- Create: `dashboard/backend/__init__.py` (empty)
- Create: `dashboard/backend/settings.py`
- Create: `dashboard/tests/__init__.py` (empty)
- Create: `dashboard/tests/conftest.py`

- [ ] **Step 1: Write `dashboard/pyproject.toml`**

```toml
[project]
name = "guardrails-dashboard"
version = "0.1.0"
description = "Admin dashboard for a NeMo Guardrails server"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "httpx>=0.27",
    "pydantic>=2",
    "pydantic-settings>=2",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["backend"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write `dashboard/backend/settings.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NGDASH_")

    guardrails_url: str = "http://127.0.0.1:8000"
    host: str = "127.0.0.1"
    port: int = 8500
    db_path: str = "~/.nemoguardrails/dashboard/dashboard.db"
    trace_globs: list[str] = []
    prom_url: str | None = None
    scrape_interval: float = 15.0
    usage_stats_path: str = "~/.config/nemoguardrails/usage_stats.json"
    static_dir: str = "frontend/dist"
```

- [ ] **Step 3: Write `dashboard/tests/conftest.py`**

```python
import pytest

from backend.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        guardrails_url="http://guardrails:8000",
        db_path=str(tmp_path / "dashboard.db"),
        trace_globs=[],
        prom_url=None,
    )
```

- [ ] **Step 4: Lock and verify the environment**

Run: `cd dashboard && uv lock && uv run python -c "from backend.settings import Settings; print(Settings().port)"`
Expected: prints `8500`

- [ ] **Step 5: Commit**

```bash
git add dashboard/pyproject.toml dashboard/uv.lock dashboard/backend/__init__.py dashboard/backend/settings.py dashboard/tests/__init__.py dashboard/tests/conftest.py
git commit -m "feat(dashboard): scaffold uv project with settings"
```

---

### Task 2: RequestRecord model and sqlite Database layer

**Files:**
- Create: `dashboard/backend/models.py`
- Create: `dashboard/backend/db.py`
- Test: `dashboard/tests/test_db.py`

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_db.py`)**

```python
import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.models'`

- [ ] **Step 3: Write `dashboard/backend/models.py`**

```python
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
```

- [ ] **Step 4: Write `dashboard/backend/db.py`**

```python
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
        if rec.interaction_id:
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

    def metric_series(
        self, name_prefix: str, start_ts: int, end_ts: int, limit: int = 5000
    ) -> list[dict]:
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
            "INSERT INTO ingest_state (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_db.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add dashboard/backend/models.py dashboard/backend/db.py dashboard/tests/test_db.py
git commit -m "feat(dashboard): add request record model and sqlite storage layer"
```

---

### Task 3: Record normalization (chat response, SSE stream, trace line)

**Files:**
- Create: `dashboard/backend/normalize.py`
- Test: `dashboard/tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_normalize.py`)**

```python
import json

from backend.normalize import record_from_chat, record_from_stream, record_from_trace_line

CHAT_RESPONSE = {
    "id": "chatcmpl-1",
    "choices": [{"message": {"role": "assistant", "content": "I cannot help with that."}, "finish_reason": "stop"}],
    "guardrails": {
        "config_id": "demo",
        "log": {
            "activated_rails": [
                {"type": "input", "name": "self check input", "decisions": [], "stop": True,
                 "started_at": 1.0, "finished_at": 1.2, "duration": 0.2},
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
                {"task": "self check", "duration": 0.9, "prompt_tokens": 42, "completion_tokens": 7,
                 "total_tokens": 49, "started_at": 1.1, "finished_at": 2.0,
                 "llm_model_name": "gpt-4", "llm_provider_name": "openai", "from_cache": False},
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
        {"name": "interaction", "span_type": "InteractionSpan", "duration": 2.0,
         "start_time": 0.0, "end_time": 2.0,
         "attributes": {"span.kind": "server", "gen_ai.operation.name": "chat"}},
        {"name": "self check input", "span_type": "RailSpan", "duration": 0.3,
         "start_time": 0.0, "end_time": 0.3,
         "attributes": {"rail.type": "input", "rail.name": "self check input", "rail.stop": True}},
        {"name": "generate bot message", "span_type": "LLMSpan", "duration": 1.0,
         "start_time": 0.5, "end_time": 1.5,
         "attributes": {"gen_ai.provider.name": "openai", "gen_ai.request.model": "gpt-4",
                        "gen_ai.response.model": "gpt-4", "gen_ai.usage.input_tokens": 10,
                        "gen_ai.usage.output_tokens": 5, "gen_ai.usage.total_tokens": 15,
                        "llm.cache.hit": False}},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.normalize'`

- [ ] **Step 3: Write `dashboard/backend/normalize.py`**

```python
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


def record_from_chat(
    body: dict[str, Any], data: dict[str, Any], source: str = "proxy"
) -> RequestRecord:
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
            payload = line[len("data:"):].strip()
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
            error = err.get("message") or str(err)

    if error is not None:
        status = "error"
    elif any(r["stop"] for r in rails):
        status = "blocked"
    else:
        status = "allowed"

    end_times = [s.get("end_time") for s in spans if s.get("end_time") is not None]
    phases = {"total_duration": max(end_times)} if end_times else {}

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_normalize.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/normalize.py dashboard/tests/test_normalize.py
git commit -m "feat(dashboard): normalize chat, stream, and trace data into records"
```

---

### Task 4: Aggregate queries (overview stats, rails frequency)

**Files:**
- Create: `dashboard/backend/queries.py`
- Test: `dashboard/tests/test_queries.py`

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_queries.py`)**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_queries.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.queries'`

- [ ] **Step 3: Write `dashboard/backend/queries.py`**

```python
import json
import math
from collections import Counter

from .db import Database


def overview_stats(db: Database, start_ts: int, end_ts: int, bucket_count: int = 60) -> dict:
    rows = db.query(
        "SELECT ts, status, phase_durations_json, llm_calls_json FROM request_records"
        " WHERE ts >= ? AND ts <= ?",
        (start_ts, end_ts),
    )
    durations: list[float] = []
    input_tokens = 0
    output_tokens = 0
    blocked = 0
    errors = 0
    bucket_span = max(1, (end_ts - start_ts) // bucket_count)
    buckets: dict[int, dict] = {}

    for row in rows:
        if row["status"] == "blocked":
            blocked += 1
        if row["status"] == "error":
            errors += 1
        phases = json.loads(row["phase_durations_json"] or "{}")
        if phases.get("total_duration") is not None:
            durations.append(phases["total_duration"])
        for call in json.loads(row["llm_calls_json"] or "[]"):
            input_tokens += call.get("prompt_tokens") or 0
            output_tokens += call.get("completion_tokens") or 0
        idx = (row["ts"] - start_ts) // bucket_span
        bucket = buckets.setdefault(
            idx, {"ts": start_ts + idx * bucket_span, "count": 0, "blocked": 0}
        )
        bucket["count"] += 1
        if row["status"] == "blocked":
            bucket["blocked"] += 1

    durations.sort()

    def percentile(p: float) -> float | None:
        if not durations:
            return None
        idx = max(0, min(len(durations) - 1, math.ceil(p / 100 * len(durations)) - 1))
        return durations[idx] * 1000

    return {
        "count": len(rows),
        "blocked": blocked,
        "errors": errors,
        "p50_ms": percentile(50),
        "p95_ms": percentile(95),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "buckets": [buckets[k] for k in sorted(buckets)],
    }


def rails_frequency(db: Database, start_ts: int, end_ts: int, limit: int = 10) -> list[dict]:
    rows = db.query(
        "SELECT rails_json FROM request_records WHERE ts >= ? AND ts <= ?",
        (start_ts, end_ts),
    )
    counts: Counter = Counter()
    blocked_counts: Counter = Counter()
    for row in rows:
        for rail in json.loads(row["rails_json"] or "[]"):
            name = rail.get("name")
            if not name:
                continue
            counts[name] += 1
            if rail.get("stop"):
                blocked_counts[name] += 1
    return [
        {"name": name, "count": count, "blocked": blocked_counts.get(name, 0)}
        for name, count in counts.most_common(limit)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_queries.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/queries.py dashboard/tests/test_queries.py
git commit -m "feat(dashboard): add overview stats and rails frequency aggregates"
```

---

### Task 5: GuardrailsClient — typed client for the guardrails server

**Files:**
- Create: `dashboard/backend/guardrails_client.py`
- Create: `dashboard/backend/deps.py`
- Test: `dashboard/tests/test_guardrails_client.py`

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_guardrails_client.py`)**

```python
import httpx
import pytest
import respx

from backend.guardrails_client import GuardrailsClient

BASE = "http://guardrails:8000"


@pytest.fixture
def client():
    http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    yield GuardrailsClient(BASE, http)
    import asyncio

    asyncio.get_event_loop().run_until_complete(http.aclose())


@respx.mock
async def test_health_ok(client):
    respx.get(f"{BASE}/v1/health").mock(return_value=httpx.Response(200, json={"status": "pass"}))
    assert await client.health() == {"status": "pass"}


@respx.mock
async def test_health_unreachable_returns_none(client):
    respx.get(f"{BASE}/v1/health").mock(side_effect=httpx.ConnectError("refused"))
    assert await client.health() is None


@respx.mock
async def test_configs_and_models_and_challenges(client):
    respx.get(f"{BASE}/v1/rails/configs").mock(return_value=httpx.Response(200, json=[{"id": "demo"}]))
    respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(200, json={"data": [{"id": "gpt-4"}]}))
    respx.get(f"{BASE}/v1/challenges").mock(return_value=httpx.Response(200, json=[{"name": "c1"}]))
    assert await client.configs() == [{"id": "demo"}]
    assert await client.models() == {"data": [{"id": "gpt-4"}]}
    assert await client.challenges() == [{"name": "c1"}]


@respx.mock
async def test_admin_capabilities_probe(client):
    respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(200, json={"admin": True}))
    assert await client.admin_capabilities() == {"admin": True}

    respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(404))
    assert await client.admin_capabilities() is None

    respx.get(f"{BASE}/v1/admin/capabilities").mock(side_effect=httpx.ConnectError("refused"))
    assert await client.admin_capabilities() is None


@respx.mock
async def test_admin_reload_posts_config_id(client):
    route = respx.post(f"{BASE}/v1/admin/reload").mock(return_value=httpx.Response(200, json={"reloaded": ["demo"]}))
    result = await client.admin_reload("demo")
    assert result == {"reloaded": ["demo"]}
    assert route.calls.last.request.content == b'{"config_id": "demo"}'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_guardrails_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.guardrails_client'`

- [ ] **Step 3: Write `dashboard/backend/deps.py`**

```python
from dataclasses import dataclass

import httpx

from .db import Database, RecordWriter
from .guardrails_client import GuardrailsClient
from .settings import Settings


@dataclass
class Deps:
    settings: Settings
    db: Database
    writer: RecordWriter
    http: httpx.AsyncClient
    client: GuardrailsClient
```

- [ ] **Step 4: Write `dashboard/backend/guardrails_client.py`**

```python
import json
from typing import Any

import httpx


class GuardrailsClient:
    """Thin async client for a running guardrails server."""

    def __init__(self, base_url: str, http: httpx.AsyncClient):
        self._base = base_url.rstrip("/")
        self._http = http

    async def _get_json(self, path: str) -> Any | None:
        try:
            resp = await self._http.get(f"{self._base}{path}")
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None

    async def health(self) -> dict | None:
        return await self._get_json("/v1/health")

    async def configs(self) -> list | None:
        return await self._get_json("/v1/rails/configs")

    async def models(self) -> Any | None:
        return await self._get_json("/v1/models")

    async def challenges(self) -> list | None:
        return await self._get_json("/v1/challenges")

    async def admin_capabilities(self) -> dict | None:
        return await self._get_json("/v1/admin/capabilities")

    async def admin_reload(self, config_id: str | None = None) -> dict | None:
        try:
            resp = await self._http.post(
                f"{self._base}/v1/admin/reload",
                json={"config_id": config_id},
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_guardrails_client.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add dashboard/backend/guardrails_client.py dashboard/backend/deps.py dashboard/tests/test_guardrails_client.py
git commit -m "feat(dashboard): add typed guardrails server client"
```

---

### Task 6: Recording proxy, non-streaming

**Files:**
- Create: `dashboard/backend/proxy.py`
- Test: `dashboard/tests/test_proxy.py` (non-streaming tests)

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_proxy.py`)**

```python
import json

import httpx
import respx
from starlette.testclient import TestClient

from backend.db import Database, RecordWriter
from backend.deps import Deps
from backend.guardrails_client import GuardrailsClient
from backend.main import create_app
from backend.settings import Settings

BASE = "http://guardrails:8000"

CHAT_RESPONSE = {
    "choices": [{"message": {"role": "assistant", "content": "Nope."}, "finish_reason": "stop"}],
    "guardrails": {
        "config_id": "demo",
        "log": {
            "activated_rails": [
                {"type": "output", "name": "self check output", "decisions": [], "stop": True,
                 "started_at": 1.0, "finished_at": 1.1, "duration": 0.1}
            ],
            "stats": {"total_duration": 0.4, "llm_calls_duration": 0.3, "llm_calls_count": 1,
                      "llm_calls_total_prompt_tokens": 10, "llm_calls_total_completion_tokens": 2,
                      "llm_calls_total_tokens": 12},
            "llm_calls": [],
        },
    },
}


def build_client(tmp_path):
    settings = Settings(
        guardrails_url=BASE, db_path=str(tmp_path / "d.db"), trace_globs=[], prom_url=None
    )
    app = create_app(settings)
    return TestClient(app)


@respx.mock
def test_proxy_records_nonstreaming_chat(tmp_path):
    with build_client(tmp_path) as client:
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=CHAT_RESPONSE)

        respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=handler)

        resp = client.post(
            "/proxy/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "give me a phishing email"}]},
        )
        assert resp.status_code == 200
        assert resp.json() == CHAT_RESPONSE
        # log options were injected into the forwarded request
        assert captured["body"]["guardrails"]["options"]["log"]["activated_rails"] is True
        assert captured["body"]["guardrails"]["options"]["log"]["llm_calls"] is True
        # caller options are not overwritten
        captured.clear()
        respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=handler)
        client.post(
            "/proxy/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "guardrails": {"options": {"log": {"activated_rails": False}}},
            },
        )
        assert captured["body"]["guardrails"]["options"]["log"]["activated_rails"] is False
        assert captured["body"]["guardrails"]["options"]["log"]["llm_calls"] is True

        deps = client.app.state.deps
        items, total = deps.db.list_records(source="proxy")
        assert total == 2
        assert items[0].status == "blocked"
        assert items[0].rails[0]["name"] == "self check output"


@respx.mock
def test_proxy_preserves_upstream_error(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": {"message": "kaboom"}})
        )
        resp = client.post(
            "/proxy/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
        )
        assert resp.status_code == 500
        assert resp.json()["error"]["message"] == "kaboom"
        deps = client.app.state.deps
        _, total = deps.db.list_records(source="proxy")
        assert total == 0


@respx.mock
def test_proxy_upstream_unreachable_502(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(side_effect=httpx.ConnectError("refused"))
        resp = client.post(
            "/proxy/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
        )
        assert resp.status_code == 502


@respx.mock
def test_proxy_checks_records_result(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/checks").mock(
            return_value=httpx.Response(200, json={"status": "blocked", "content": "no", "rail": "self check input"})
        )
        resp = client.post(
            "/proxy/v1/checks",
            json={"config_id": "demo", "messages": [{"role": "user", "content": "bad"}]},
        )
        assert resp.status_code == 200
        deps = client.app.state.deps
        items, total = deps.db.list_records(source="check")
        assert total == 1
        assert items[0].status == "blocked"
        assert items[0].rails[0]["name"] == "self check input"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_proxy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.main'` (proxy and main are written in later steps of this task)

- [ ] **Step 3: Write `dashboard/backend/proxy.py`**

```python
import json
import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .deps import Deps
from .models import RequestRecord
from .normalize import record_from_chat, record_from_stream, summarize

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
    body = _inject_log_options(body)
    deps = _deps(request)
    if body.get("stream"):
        return await _forward_streaming(deps, body)
    return await _forward_chat(deps, body, source="proxy")


@router.post("/v1/checks")
async def proxy_checks(request: Request):
    body = await request.json()
    deps = _deps(request)
    try:
        upstream = await deps.http.post(f"{deps.settings.guardrails_url}/v1/checks", json=body)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="guardrails server unreachable")
    if upstream.status_code != 200:
        return Response(upstream.content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"))
    try:
        data = upstream.json()
    except json.JSONDecodeError:
        return Response(upstream.content, status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"))
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
        upstream = await deps.http.post(
            f"{deps.settings.guardrails_url}/v1/chat/completions", json=body
        )
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
            await deps.writer.enqueue(
                record_from_stream(body, text, started, ended, source=source)
            )

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _record_from_check(body: dict, data: dict) -> RequestRecord:
    from .normalize import _last_user_message  # internal reuse

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
```

- [ ] **Step 4: Write the minimal `dashboard/backend/main.py`**

This task only wires what exists so far (proxy + writer); later tasks add routers and ingestion to `create_app`. Write it in its final shape now except leave out not-yet-existing routers:

```python
import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import Database, RecordWriter
from .deps import Deps
from .guardrails_client import GuardrailsClient
from .proxy import router as proxy_router
from .settings import Settings


def build_settings(argv: list[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser(prog="guardrails-dashboard")
    parser.add_argument("--guardrails-url", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--trace-glob", dest="trace_globs", action="append", default=None)
    parser.add_argument("--prom-url", default=None)
    parser.add_argument("--scrape-interval", type=float, default=None)
    parser.add_argument("--static-dir", default=None)
    args = parser.parse_args(argv)
    overrides = {k: v for k, v in vars(args).items() if v is not None}
    return Settings(**overrides)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings.db_path)
    writer = RecordWriter(db)
    http = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))
    deps = Deps(
        settings=settings,
        db=db,
        writer=writer,
        http=http,
        client=GuardrailsClient(settings.guardrails_url, http),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await writer.start()
        yield
        await writer.stop()
        await http.aclose()
        db.close()

    app = FastAPI(title="Guardrails Admin Dashboard", lifespan=lifespan)
    app.state.deps = deps
    app.include_router(proxy_router)
    return app


def main():
    settings = build_settings()
    import uvicorn

    app = create_app(settings)
    static = Path(settings.static_dir)
    if static.exists():
        app.mount("/", StaticFiles(directory=str(static), html=True))

    uvicorn.run(app, host=settings.host, port=settings.port)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_proxy.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add dashboard/backend/proxy.py dashboard/backend/main.py dashboard/tests/test_proxy.py
git commit -m "feat(dashboard): add recording proxy for chat completions and checks"
```

---

### Task 7: Recording proxy, streaming (SSE pass-through with tee)

**Files:**
- Modify: `dashboard/tests/test_proxy.py` (append streaming tests)

- [ ] **Step 1: Append the failing tests to `dashboard/tests/test_proxy.py`**

```python
SSE_CHUNKS = [
    b'data: {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "Stay"}}]}\n\n',
    b'data: {"choices": [{"index": 0, "delta": {"content": " safe."}}]}\n\n',
    b"data: [DONE]\n\n",
]


@respx.mock
def test_proxy_streams_sse_and_records(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=iter(SSE_CHUNKS),
            )
        )
        with client.stream(
            "POST",
            "/proxy/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = b"".join(resp.iter_raw())
        assert b"Stay" in body and b"[DONE]" in body

        deps = client.app.state.deps
        items, total = deps.db.list_records(source="proxy")
        assert total == 1
        assert items[0].output_summary == "Stay safe."
        assert items[0].phase_durations["total_duration"] >= 0
        assert items[0].status == "allowed"


@respx.mock
def test_proxy_streaming_upstream_error(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": {"message": "upstream boom"}})
        )
        with client.stream(
            "POST",
            "/proxy/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        ) as resp:
            body = b"".join(resp.iter_raw())
        assert b"upstream boom" in body
        deps = client.app.state.deps
        _, total = deps.db.list_records(source="proxy")
        assert total == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_proxy.py -k stream -v`
Expected: FAIL. `test_proxy_streaming_upstream_error` fails because the current `_forward_streaming` yields the error body but the recorded assertion may already pass; the likely failure is in `test_proxy_streams_sse_and_records` (record not written or output mismatch). If both pass unexpectedly, inspect: the current implementation already tees; in that case run the full file and confirm all 6 pass, then treat Step 3 as already satisfied and move to Step 4.

- [ ] **Step 3: Implement `_forward_streaming` in `dashboard/backend/proxy.py`**

If Step 2 failed, replace the existing `_forward_streaming` with this exact version (it is also the reference for what the function must do):

```python
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
```

- [ ] **Step 4: Run all proxy tests**

Run: `cd dashboard && uv run pytest tests/test_proxy.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/proxy.py dashboard/tests/test_proxy.py
git commit -m "feat(dashboard): stream SSE pass-through with recording tee"
```

---

### Task 8: Trace file ingestion (JSONL tailing)

**Files:**
- Create: `dashboard/backend/ingest.py` (trace part)
- Test: `dashboard/tests/test_ingest.py` (trace tests)

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_ingest.py`)**

```python
import json

import pytest

from backend.db import Database, RecordWriter
from backend.ingest import TraceIngester

TRACE_LINE = {
    "schema_version": "2.0",
    "trace_id": "t-1",
    "spans": [
        {"name": "interaction", "span_type": "InteractionSpan", "duration": 1.0,
         "start_time": 0.0, "end_time": 1.0, "attributes": {}},
        {"name": "self check input", "span_type": "RailSpan", "duration": 0.2,
         "start_time": 0.0, "end_time": 0.2,
         "attributes": {"rail.type": "input", "rail.name": "self check input", "rail.stop": True}},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.ingest'`

- [ ] **Step 3: Write `dashboard/backend/ingest.py` (trace part)**

```python
import asyncio
import glob
import json
import os
import time

from .db import Database, RecordWriter
from .normalize import record_from_trace_line


class TraceIngester:
    """Tails trace JSONL files produced by the guardrails FileSystem adapter."""

    def __init__(self, db: Database, writer: RecordWriter, globs: list[str]):
        self._db = db
        self._writer = writer
        self._globs = globs

    async def run_forever(self, interval: float = 5.0):
        while True:
            await self.scan_once()
            await asyncio.sleep(interval)

    def _files(self) -> list[str]:
        found: list[str] = []
        for pattern in self._globs:
            found.extend(glob.glob(pattern))
        return sorted(set(found))

    async def scan_once(self):
        for path in self._files():
            await self._scan_file(path)

    async def _scan_file(self, path: str):
        try:
            size = os.path.getsize(path)
        except OSError:
            return
        state_key = f"trace:{path}"
        malformed_key = f"malformed:{path}"
        try:
            offset = int(self._db.get_state(state_key) or 0)
        except ValueError:
            offset = 0
        if size < offset:
            offset = 0  # rotated or truncated
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
        self._db.set_state(state_key, str(offset + len(data)))
        if not data:
            return
        mtime_ms = int(os.path.getmtime(path) * 1000)
        for raw_line in data.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                self._db.increment_state(malformed_key)
                continue
            await self._writer.enqueue(record_from_trace_line(entry, ts_ms=mtime_ms))


def now_ms() -> int:
    return int(time.time() * 1000)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_ingest.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/ingest.py dashboard/tests/test_ingest.py
git commit -m "feat(dashboard): tail trace JSONL files into request records"
```

---

### Task 9: Prometheus scraping and text-format parsing

**Files:**
- Modify: `dashboard/backend/ingest.py` (append prometheus part)
- Test: `dashboard/tests/test_ingest.py` (append prometheus tests)

- [ ] **Step 1: Append the failing tests to `dashboard/tests/test_ingest.py`**

```python
import httpx
import respx

from backend.ingest import parse_prometheus_text, scrape_prometheus_once

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
    assert by_name["http_requests_total"] == [
        ({'handler': '/v1/chat/completions', 'code': '200'}, 42.5)
    ]


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
    series = db.metric_series("guardrails_nonstream", 0, 9_999_999_999)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_ingest.py -k prom -v`
Expected: FAIL with `ImportError: cannot import name 'parse_prometheus_text'`

- [ ] **Step 3: Append the prometheus part to `dashboard/backend/ingest.py`**

```python
import re

import httpx

_SAMPLE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+(\S+)")
_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def parse_prometheus_text(text: str) -> list[tuple[str, dict, float]]:
    """Parse the Prometheus text exposition format into (name, labels, value)."""
    samples: list[tuple[str, dict, float]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        name, label_src, value_src = match.groups()
        try:
            value = float(value_src)
        except ValueError:
            continue
        labels = {k: v.replace('\\"', '"') for k, v in _LABEL_RE.findall(label_src or "")}
        samples.append((name, labels, value))
    return samples


async def scrape_prometheus_once(db: Database, http: httpx.AsyncClient, prom_url: str):
    try:
        resp = await http.get(prom_url)
    except httpx.HTTPError:
        return
    if resp.status_code != 200:
        return
    ts = now_ms()
    samples = [
        (name, json.dumps(labels), ts, value)
        for name, labels, value in parse_prometheus_text(resp.text)
    ]
    db.insert_samples(samples)


async def prometheus_loop(db: Database, http: httpx.AsyncClient, prom_url: str, interval: float):
    while True:
        await scrape_prometheus_once(db, http, prom_url)
        await asyncio.sleep(interval)
```

Also update the imports at the top of `ingest.py` to include `re` and `httpx` (add to the existing import block).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_ingest.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/ingest.py dashboard/tests/test_ingest.py
git commit -m "feat(dashboard): scrape prometheus metrics into sqlite"
```

---

### Task 10: Usage telemetry reader

**Files:**
- Create: `dashboard/backend/telemetry.py`
- Test: `dashboard/tests/test_telemetry.py`

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_telemetry.py`)**

```python
import json

from backend.telemetry import read_usage_events

EVENT = {
    "nemoSource": "nemoguardrails",
    "event": "heartbeat",
    "sessionId": "s-1",
    "timestamp": 1720000000.0,
    "nemoguardrailsVersion": "0.10.0",
    "railTypesInUse": ["input", "output"],
    "numRailsConfigured": 5,
    "llmProviders": ["openai"],
    "deploymentType": "api",
    "railsEngine": "LLMRails",
    "tracingEnabled": False,
    "streamingConfigured": True,
    "hasKnowledgeBase": False,
    "numCustomFlows": 2,
    "builtinFeatures": [],
    "pythonVersion": "3.10.0",
    "platform": "Linux",
    "osName": "Linux",
    "colangVersion": "1.0",
}


def test_reads_last_n_events(tmp_path):
    path = tmp_path / "usage_stats.json"
    lines = [dict(EVENT, event="startup", timestamp=float(i)) for i in range(10)]
    path.write_text("\n".join(json.dumps(e) for e in lines) + "\n")
    events = read_usage_events(str(path), limit=3)
    assert len(events) == 3
    assert events[-1]["timestamp"] == 9.0
    assert events[0]["timestamp"] == 7.0


def test_missing_file_returns_empty(tmp_path):
    assert read_usage_events(str(tmp_path / "nope.json")) == []


def test_malformed_lines_skipped(tmp_path):
    path = tmp_path / "usage_stats.json"
    path.write_text("garbage\n" + json.dumps(EVENT) + "\n")
    events = read_usage_events(str(path))
    assert len(events) == 1
    assert events[0]["event"] == "heartbeat"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_telemetry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.telemetry'`

- [ ] **Step 3: Write `dashboard/backend/telemetry.py`**

```python
import json
from pathlib import Path
from typing import Any


def read_usage_events(path: str, limit: int = 200) -> list[dict[str, Any]]:
    """Read the local anonymous-usage telemetry audit file (JSONL). Read-only."""
    target = Path(path).expanduser()
    if not target.exists():
        return []
    events: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events[-limit:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_telemetry.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/telemetry.py dashboard/tests/test_telemetry.py
git commit -m "feat(dashboard): read local usage telemetry events"
```

---

### Task 11: Dashboard REST API — status, requests, metrics, telemetry

**Files:**
- Create: `dashboard/backend/api/__init__.py` (empty)
- Create: `dashboard/backend/api/status.py`
- Create: `dashboard/backend/api/requests.py`
- Create: `dashboard/backend/api/metrics.py`
- Create: `dashboard/backend/api/telemetry.py`
- Modify: `dashboard/backend/main.py` (include the new routers)
- Test: `dashboard/tests/test_api.py`

- [ ] **Step 1: Write the failing tests (`dashboard/tests/test_api.py`)**

```python
import httpx
import respx
from starlette.testclient import TestClient

from backend.db import Database
from backend.main import create_app
from backend.models import RequestRecord
from backend.settings import Settings

BASE = "http://guardrails:8000"


def build_client(tmp_path, **overrides):
    settings = Settings(
        guardrails_url=BASE, db_path=str(tmp_path / "d.db"), trace_globs=[], prom_url=None,
        **overrides,
    )
    return TestClient(create_app(settings))


def seed_record(db):
    db.insert_record(
        RequestRecord(
            id="r1", ts=5000, source="proxy", status="blocked", config_id="demo",
            input_summary="bad request", output_summary="refused",
            rails=[{"name": "self check input", "stop": True}],
            llm_calls=[{"model": "gpt-4", "prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}],
            phase_durations={"total_duration": 0.5},
        )
    )


@respx.mock
def test_status_endpoint_reports_server_and_hook(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/health").mock(return_value=httpx.Response(200, json={"status": "pass"}))
        respx.get(f"{BASE}/v1/rails/configs").mock(return_value=httpx.Response(200, json=[{"id": "demo"}]))
        respx.get(f"{BASE}/v1/models").mock(return_value=httpx.Response(200, json={"data": []}))
        respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(404))

        data = client.get("/api/status").json()
        assert data["guardrails"]["healthy"] is True
        assert data["guardrails"]["configs"] == [{"id": "demo"}]
        assert data["admin_hook"] is False
        assert "ingestion" in data


@respx.mock
def test_status_when_server_down(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/health").mock(side_effect=httpx.ConnectError("refused"))
        respx.get(f"{BASE}/v1/rails/configs").mock(side_effect=httpx.ConnectError("refused"))
        respx.get(f"{BASE}/v1/models").mock(side_effect=httpx.ConnectError("refused"))
        respx.get(f"{BASE}/v1/admin/capabilities").mock(side_effect=httpx.ConnectError("refused"))

        data = client.get("/api/status").json()
        assert data["guardrails"]["healthy"] is False
        assert data["guardrails"]["configs"] is None


def test_requests_list_and_detail(tmp_path):
    with build_client(tmp_path) as client:
        seed_record(client.app.state.deps.db)
        data = client.get("/api/requests").json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "r1"
        assert data["items"][0]["status"] == "blocked"

        data = client.get("/api/requests", params={"status": "allowed"}).json()
        assert data["total"] == 0

        data = client.get("/api/requests", params={"search": "bad"}).json()
        assert data["total"] == 1

        detail = client.get("/api/requests/r1").json()
        assert detail["rails"][0]["name"] == "self check input"
        assert client.get("/api/requests/nope").status_code == 404


def test_metrics_overview_and_rails(tmp_path):
    with build_client(tmp_path) as client:
        seed_record(client.app.state.deps.db)
        params = {"start": 0, "end": 9_999_999_999_999}
        data = client.get("/api/metrics/overview", params=params).json()
        assert data["count"] == 1
        assert data["blocked"] == 1
        assert data["input_tokens"] == 1

        rails = client.get("/api/metrics/rails", params=params).json()
        assert rails[0]["name"] == "self check input"
        assert rails[0]["blocked"] == 1


def test_metrics_series(tmp_path):
    with build_client(tmp_path) as client:
        db = client.app.state.deps.db
        db.insert_samples([("guardrails_nonstream_queued", "{}", 1000, 3.0)])
        data = client.get("/api/metrics/series", params={"name_prefix": "guardrails_nonstream"}).json()
        assert len(data) == 1
        assert data[0]["value"] == 3.0


def test_telemetry_endpoint(tmp_path):
    usage = tmp_path / "usage_stats.json"
    usage.write_text('{"event": "startup", "timestamp": 1.0}\n')
    with build_client(tmp_path, usage_stats_path=str(usage)) as client:
        data = client.get("/api/telemetry/events").json()
        assert data["items"] == [{"event": "startup", "timestamp": 1.0}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_api.py -v`
Expected: FAIL with 404s on `/api/status` etc. (`ModuleNotFoundError` if a router file is missing)

- [ ] **Step 3: Write `dashboard/backend/api/__init__.py`** (empty file)

- [ ] **Step 4: Write `dashboard/backend/api/status.py`**

```python
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/status")
async def get_status(request: Request):
    deps = request.app.state.deps
    health = await deps.client.health()
    configs = await deps.client.configs()
    models = await deps.client.models()
    capabilities = await deps.client.admin_capabilities()

    malformed = {}
    for row in deps.db.query("SELECT key, value FROM ingest_state WHERE key LIKE 'malformed:%'"):
        malformed[row["key"][len("malformed:"):]] = int(row["value"])

    return {
        "guardrails": {
            "url": deps.settings.guardrails_url,
            "healthy": health is not None,
            "configs": configs,
            "models": models,
        },
        "ingestion": {
            "trace_globs": deps.settings.trace_globs,
            "prom_url": deps.settings.prom_url,
            "malformed": malformed,
            "records_written": deps.writer.written,
            "records_dropped_duplicates": deps.writer.dropped,
        },
        "admin_hook": capabilities is not None,
    }
```

- [ ] **Step 5: Write `dashboard/backend/api/requests.py`**

```python
from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/api")


@router.get("/requests")
async def list_requests(
    request: Request,
    start: int | None = None,
    end: int | None = None,
    status: str | None = None,
    source: str | None = None,
    config_id: str | None = None,
    rail: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    deps = request.app.state.deps
    items, total = deps.db.list_records(
        start_ts=start,
        end_ts=end,
        status=status,
        source=source,
        config_id=config_id,
        rail=rail,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {"items": [r.to_dict() for r in items], "total": total}


@router.get("/requests/{record_id}")
async def get_request(record_id: str, request: Request):
    deps = request.app.state.deps
    rec = deps.db.get_record(record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="record not found")
    return rec.to_dict()
```

- [ ] **Step 6: Write `dashboard/backend/api/metrics.py`**

```python
import time

from fastapi import APIRouter, Query, Request

from ..queries import overview_stats, rails_frequency

router = APIRouter(prefix="/api/metrics")


def _range(start: int | None, end: int | None) -> tuple[int, int]:
    now = int(time.time() * 1000)
    return (start if start is not None else now - 15 * 60 * 1000), (
        end if end is not None else now
    )


@router.get("/overview")
async def get_overview(request: Request, start: int | None = None, end: int | None = None):
    start, end = _range(start, end)
    return overview_stats(request.app.state.deps.db, start, end)


@router.get("/rails")
async def get_rails(request: Request, start: int | None = None, end: int | None = None):
    start, end = _range(start, end)
    return rails_frequency(request.app.state.deps.db, start, end)


@router.get("/series")
async def get_series(
    request: Request,
    name_prefix: str = Query(default=""),
    start: int | None = None,
    end: int | None = None,
):
    start, end = _range(start, end)
    return request.app.state.deps.db.metric_series(name_prefix, start, end)
```

- [ ] **Step 7: Write `dashboard/backend/api/telemetry.py`**

```python
from fastapi import APIRouter, Request

from ..telemetry import read_usage_events

router = APIRouter(prefix="/api/telemetry")


@router.get("/events")
async def get_events(request: Request, limit: int = 200):
    deps = request.app.state.deps
    items = read_usage_events(deps.settings.usage_stats_path, limit=limit)
    return {"items": items}
```

- [ ] **Step 8: Modify `dashboard/backend/main.py` to include the routers**

In `create_app`, after `app.include_router(proxy_router)` add:

```python
    from .api import metrics as metrics_api
    from .api import requests as requests_api
    from .api import status as status_api
    from .api import telemetry as telemetry_api

    app.include_router(status_api.router)
    app.include_router(requests_api.router)
    app.include_router(metrics_api.router)
    app.include_router(telemetry_api.router)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_api.py -v`
Expected: 7 passed

- [ ] **Step 10: Commit**

```bash
git add dashboard/backend/api/ dashboard/backend/main.py dashboard/tests/test_api.py
git commit -m "feat(dashboard): add status, requests, metrics, telemetry APIs"
```

---

### Task 12: Commands API — console, checks, challenges, reload

**Files:**
- Create: `dashboard/backend/api/commands.py`
- Modify: `dashboard/backend/main.py` (include commands router)
- Test: `dashboard/tests/test_api.py` (append command tests)

- [ ] **Step 1: Append the failing tests to `dashboard/tests/test_api.py`**

```python
CHAT_OK = {
    "choices": [{"message": {"role": "assistant", "content": "fine"}, "finish_reason": "stop"}],
    "guardrails": {"config_id": "demo", "log": {"activated_rails": [], "stats": {"total_duration": 0.2}, "llm_calls": []}},
}


@respx.mock
def test_console_run_records_with_console_source(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(200, json=CHAT_OK))
        resp = client.post(
            "/api/commands/console/run",
            json={"config_id": "demo", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "fine"
        items, total = client.app.state.deps.db.list_records(source="console")
        assert total == 1
        assert items[0].config_id == "demo"


@respx.mock
def test_checks_run_records_with_check_source(tmp_path):
    with build_client(tmp_path) as client:
        respx.post(f"{BASE}/v1/checks").mock(
            return_value=httpx.Response(200, json={"status": "allowed", "content": "ok", "rail": None})
        )
        resp = client.post(
            "/api/commands/checks/run",
            json={"config_id": "demo", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 200
        items, total = client.app.state.deps.db.list_records(source="check")
        assert total == 1


@respx.mock
def test_challenges_list_and_run(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/challenges").mock(
            return_value=httpx.Response(200, json=[{"id": "c1", "input": "hack"}, {"id": "c2", "input": "spam"}])
        )
        assert len(client.get("/api/commands/challenges").json()["items"]) == 2

        respx.post(f"{BASE}/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=CHAT_OK)
        )
        resp = client.post(
            "/api/commands/challenges/run",
            json={"config_id": "demo", "challenge_ids": ["c1"]},
        )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["challenge_id"] == "c1"
        items, total = client.app.state.deps.db.list_records(source="challenge")
        assert total == 1


@respx.mock
def test_admin_reload_without_hook_returns_409_with_instructions(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/admin/capabilities").mock(return_value=httpx.Response(404))
        resp = client.post("/api/commands/admin/reload", json={"config_id": "demo"})
        assert resp.status_code == 409
        assert "admin_hook" in resp.json()["detail"]


@respx.mock
def test_admin_reload_with_hook_forwards(tmp_path):
    with build_client(tmp_path) as client:
        respx.get(f"{BASE}/v1/admin/capabilities").mock(
            return_value=httpx.Response(200, json={"admin": True})
        )
        route = respx.post(f"{BASE}/v1/admin/reload").mock(
            return_value=httpx.Response(200, json={"reloaded": ["demo"]})
        )
        resp = client.post("/api/commands/admin/reload", json={"config_id": "demo"})
        assert resp.status_code == 200
        assert resp.json() == {"reloaded": ["demo"]}
        assert route.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_api.py -k "console or checks or challenges or admin" -v`
Expected: FAIL with 404s (commands router not wired)

- [ ] **Step 3: Write `dashboard/backend/api/commands.py`**

```python
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
```

- [ ] **Step 4: Modify `dashboard/backend/main.py`** — add `app.include_router(commands_api.router)` with the other API routers:

```python
    from .api import commands as commands_api
    ...
    app.include_router(commands_api.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard && uv run pytest tests/test_api.py -v`
Expected: 12 passed

- [ ] **Step 6: Commit**

```bash
git add dashboard/backend/api/commands.py dashboard/backend/main.py dashboard/tests/test_api.py
git commit -m "feat(dashboard): add console, checks, challenges, reload commands API"
```

---

### Task 13: Wire ingestion loops and static SPA serving into main.py

**Files:**
- Modify: `dashboard/backend/main.py`
- Test: `dashboard/tests/test_main.py`

- [ ] **Step 1: Write the failing test (`dashboard/tests/test_main.py`)**

```python
from starlette.testclient import TestClient

from backend.main import build_settings, create_app
from backend.settings import Settings


def test_build_settings_cli_overrides():
    settings = build_settings(["--guardrails-url", "http://x:1", "--port", "9999", "--db", "/tmp/a.db"])
    assert settings.guardrails_url == "http://x:1"
    assert settings.port == 9999
    assert settings.db_path == "/tmp/a.db"
    defaults = build_settings([])
    assert defaults.port == 8500


def test_create_app_starts_writer_and_tasks(tmp_path):
    settings = Settings(
        guardrails_url="http://guardrails:8000",
        db_path=str(tmp_path / "d.db"),
        trace_globs=[],
        prom_url=None,
    )
    with TestClient(create_app(settings)) as client:
        deps = client.app.state.deps
        assert deps.writer._task is not None
        assert client.get("/api/status").status_code == 200


def test_static_files_served_when_present(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets").mkdir()
    settings = Settings(
        guardrails_url="http://guardrails:8000",
        db_path=str(tmp_path / "d.db"),
        static_dir=str(dist),
    )
    with TestClient(create_app(settings)) as client:
        assert "spa" in client.get("/").text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && uv run pytest tests/test_main.py -v`
Expected: `test_static_files_served_when_present` FAILS (static mount only happens in `main()`, not `create_app`); the others should pass or fail depending on current wiring — fix by implementing Step 3.

- [ ] **Step 3: Rewrite `dashboard/backend/main.py` in its final form**

```python
import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import Database, RecordWriter
from .deps import Deps
from .guardrails_client import GuardrailsClient
from .ingest import TraceIngester, prometheus_loop
from .proxy import router as proxy_router
from .settings import Settings


def build_settings(argv: list[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser(prog="guardrails-dashboard")
    parser.add_argument("--guardrails-url", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--trace-glob", dest="trace_globs", action="append", default=None)
    parser.add_argument("--prom-url", default=None)
    parser.add_argument("--scrape-interval", type=float, default=None)
    parser.add_argument("--static-dir", default=None)
    args = parser.parse_args(argv)
    overrides = {k: v for k, v in vars(args).items() if v is not None}
    return Settings(**overrides)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db = Database(settings.db_path)
    writer = RecordWriter(db)
    http = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))
    deps = Deps(
        settings=settings,
        db=db,
        writer=writer,
        http=http,
        client=GuardrailsClient(settings.guardrails_url, http),
    )
    trace_ingester = TraceIngester(db, writer, settings.trace_globs)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await writer.start()
        tasks = []
        if settings.trace_globs:
            tasks.append(asyncio.create_task(trace_ingester.run_forever()))
        if settings.prom_url:
            tasks.append(
                asyncio.create_task(
                    prometheus_loop(db, http, settings.prom_url, settings.scrape_interval)
                )
            )
        yield
        for task in tasks:
            task.cancel()
        await writer.stop()
        await http.aclose()
        db.close()

    app = FastAPI(title="Guardrails Admin Dashboard", lifespan=lifespan)
    app.state.deps = deps

    from .api import commands as commands_api
    from .api import metrics as metrics_api
    from .api import requests as requests_api
    from .api import status as status_api
    from .api import telemetry as telemetry_api

    app.include_router(proxy_router)
    app.include_router(status_api.router)
    app.include_router(requests_api.router)
    app.include_router(metrics_api.router)
    app.include_router(telemetry_api.router)
    app.include_router(commands_api.router)

    static = Path(settings.static_dir)
    if static.exists():
        app.mount("/", StaticFiles(directory=str(static), html=True), name="static")
    return app


def main():
    settings = build_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)
```

- [ ] **Step 4: Run all backend tests**

Run: `cd dashboard && uv run pytest tests/ -v`
Expected: all pass (25+ tests)

- [ ] **Step 5: Commit**

```bash
git add dashboard/backend/main.py dashboard/tests/test_main.py
git commit -m "feat(dashboard): wire ingestion loops and static SPA serving"
```

---

### Task 14: Admin hook for the guardrails server + README

**Files:**
- Create: `dashboard/admin_hook/guardrails_admin.py`
- Create: `dashboard/README.md`

- [ ] **Step 1: Write `dashboard/admin_hook/guardrails_admin.py`**

```python
"""Admin endpoints for the Guardrails Admin Dashboard.

Drop this file into your guardrails config folder (the folder passed to
`nemoguardrails server --config` that contains your per-bot subfolders) and
wire it from the folder's config.py:

    import importlib.util
    import os

    def _load_admin_hook(app):
        path = os.path.join(os.path.dirname(__file__), "guardrails_admin.py")
        spec = importlib.util.spec_from_file_location("guardrails_admin", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.init(app)

    def init(app):
        _load_admin_hook(app)

The hook is only loaded by the server when the config root is not in
single-config mode (see nemoguardrails/server/api.py).
"""


def init(app):
    from nemoguardrails.server import api as server_api

    @app.get("/v1/admin/capabilities")
    async def admin_capabilities():
        return {"admin": True, "reload": True}

    @app.post("/v1/admin/reload")
    async def admin_reload(config_id: str | None = None):
        """Drop cached LLMRails instances so configs rebuild on next request.

        Mirrors the built-in auto-reload behavior, but also matches merged
        config keys ("id1-id2") and model-suffixed keys ("id:model").
        """
        reloaded = []
        for key in list(server_api.llm_rails_instances.keys()):
            ids = key.split(":")[0].split("-")
            if config_id is None or config_id in ids:
                instance = server_api.llm_rails_instances.pop(key)
                reloaded.append(key)
                if instance is not None and hasattr(instance, "events_history_cache"):
                    server_api.llm_rails_events_history_cache[key] = instance.events_history_cache
        return {"reloaded": reloaded}
```

- [ ] **Step 2: Write `dashboard/README.md`**

````markdown
# Guardrails Admin Dashboard

A local, single-user web dashboard for a running NeMo Guardrails server:
record and inspect per-request data (activated rails, decisions, durations,
LLM calls, tokens), view metrics and usage telemetry, and issue commands to
the server (test prompts, checks, red-teaming challenges, config reload).

## Requirements

- Python 3.10+ with [uv](https://docs.astral.sh/uv/)
- Node.js 22+ (only to build the frontend)
- A running guardrails server (`nemoguardrails server --config ...`)

## Quick start

```bash
cd dashboard
uv sync

# build the frontend once
cd frontend && npm install && npm run build && cd ..

# run the dashboard
uv run python -m backend.main --guardrails-url http://127.0.0.1:8000
```

Open http://127.0.0.1:8500.

## Data collection

The dashboard collects data three ways (all optional):

1. **Recording proxy** (default): point clients at
   `http://127.0.0.1:8500/proxy` instead of the guardrails server. Chat and
   checks are forwarded, and the generation log from each response is stored.
   Streaming responses pass through unchanged and are recorded on completion.
2. **Trace files**: pass `--trace-glob "<app>/.traces/*.jsonl"` to ingest the
   JSONL written by the guardrails FileSystem tracing adapter.
3. **Prometheus**: pass `--prom-url http://127.0.0.1:9464/metrics` to scrape
   the guardrails server metrics exporter.

Usage telemetry is read from `~/.config/nemoguardrails/usage_stats.json`.

## Config reload (optional server hook)

The guardrails server has no reload endpoint. To enable the dashboard's
Reload button, copy `admin_hook/guardrails_admin.py` into your guardrails
config folder and add to that folder's `config.py`:

```python
import importlib.util
import os

def _load_admin_hook(app):
    path = os.path.join(os.path.dirname(__file__), "guardrails_admin.py")
    spec = importlib.util.spec_from_file_location("guardrails_admin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.init(app)

def init(app):
    _load_admin_hook(app)
```

## Development

```bash
cd dashboard
uv run pytest                      # backend tests
cd frontend && npm run test        # frontend tests
npm run dev                        # SPA dev server (proxies /api and /proxy to :8500)
```

## Notes and limitations

- Local single-user tool: no authentication. Do not expose it to a network.
- Streaming records capture output text and measured latency only (the
  guardrails generation log is not returned for streaming responses).
- `thread_id` in the Console requires the guardrails server to have a
  datastore registered (the server returns 400 otherwise).
- Trace-ingested records use the trace file mtime as their timestamp.
````

- [ ] **Step 3: Verify the hook file parses**

Run: `cd dashboard && uv run python -c "import ast; ast.parse(open('admin_hook/guardrails_admin.py').read())"`
Expected: no output (exit 0)

- [ ] **Step 4: Commit**

```bash
git add dashboard/admin_hook/guardrails_admin.py dashboard/README.md
git commit -m "feat(dashboard): add admin reload hook and README"
```

---

### Task 15: Frontend scaffold (Vite + React + TS)

**Files:**
- Create: `dashboard/frontend/package.json`
- Create: `dashboard/frontend/vite.config.ts`
- Create: `dashboard/frontend/tsconfig.json`
- Create: `dashboard/frontend/index.html`
- Create: `dashboard/frontend/src/main.tsx`
- Create: `dashboard/frontend/src/App.tsx` (placeholder, replaced in Task 17)

- [ ] **Step 1: Write `dashboard/frontend/package.json`**

```json
{
  "name": "guardrails-dashboard-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "recharts": "^2.12.7"
  },
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^24.1.0",
    "typescript": "^5.5.3",
    "vite": "^5.3.4",
    "vitest": "^2.0.3"
  }
}
```

- [ ] **Step 2: Write `dashboard/frontend/vite.config.ts`**

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8500",
      "/proxy": "http://127.0.0.1:8500",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

- [ ] **Step 3: Write `dashboard/frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals"]
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write `dashboard/frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Guardrails Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Write `dashboard/frontend/src/main.tsx`**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 6: Write placeholder `dashboard/frontend/src/App.tsx`**

```tsx
export default function App() {
  return <h1>Guardrails Dashboard</h1>;
}
```

- [ ] **Step 7: Install and verify the build**

Run: `cd dashboard/frontend && npm install && npm run build`
Expected: `tsc --noEmit` passes, `vite build` emits `dist/index.html`

- [ ] **Step 8: Commit**

```bash
git add dashboard/frontend/package.json dashboard/frontend/package-lock.json dashboard/frontend/vite.config.ts dashboard/frontend/tsconfig.json dashboard/frontend/index.html dashboard/frontend/src/main.tsx dashboard/frontend/src/App.tsx
git commit -m "feat(dashboard): scaffold vite react frontend"
```

---

### Task 16: Frontend API client and types

**Files:**
- Create: `dashboard/frontend/src/types.ts`
- Create: `dashboard/frontend/src/api.ts`
- Test: `dashboard/frontend/src/api.test.ts`

- [ ] **Step 1: Write the failing test (`dashboard/frontend/src/api.test.ts`)**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("builds query strings and unwraps responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.records({ status: "blocked", search: "", limit: 10 });
    expect(result).toEqual({ items: [], total: 0 });
    const url = new URL(fetchMock.mock.calls[0][0] as string, "http://localhost");
    expect(url.pathname).toBe("/api/requests");
    expect(url.searchParams.get("status")).toBe("blocked");
    expect(url.searchParams.get("search")).toBeNull();
    expect(url.searchParams.get("limit")).toBe("10");
  });

  it("throws ApiError with the server detail message", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "guardrails server unreachable" }), {
        status: 502,
        statusText: "Bad Gateway",
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.status()).rejects.toThrow(ApiError);
    await expect(api.status()).rejects.toThrow("guardrails server unreachable");
  });

  it("sends JSON bodies for POST requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.adminReload("demo");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/commands/admin/reload");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ config_id: "demo" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard/frontend && npx vitest run src/api.test.ts`
Expected: FAIL with `Cannot find module './api'`

- [ ] **Step 3: Write `dashboard/frontend/src/types.ts`**

```ts
export interface RailInfo {
  type?: string;
  name?: string;
  stop: boolean;
  duration?: number;
  decisions?: string[];
}

export interface LlmCall {
  task?: string;
  provider?: string;
  model?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  duration?: number;
  from_cache?: boolean;
}

export interface RequestRecord {
  id: string;
  ts: number;
  source: string;
  status: string;
  interaction_id?: string | null;
  config_id?: string | null;
  thread_id?: string | null;
  input_summary: string;
  output_summary: string;
  rails: RailInfo[];
  llm_calls: LlmCall[];
  phase_durations: Record<string, number>;
  error?: string | null;
  raw_request?: unknown;
  raw_response?: unknown;
}

export interface RecordsResponse {
  items: RequestRecord[];
  total: number;
}

export interface GuardrailsStatus {
  url: string;
  healthy: boolean;
  configs: { id: string }[] | null;
  models: unknown;
}

export interface StatusResponse {
  guardrails: GuardrailsStatus;
  ingestion: {
    trace_globs: string[];
    prom_url?: string | null;
    malformed: Record<string, number>;
    records_written: number;
    records_dropped_duplicates: number;
  };
  admin_hook: boolean;
}

export interface OverviewStats {
  count: number;
  blocked: number;
  errors: number;
  p50_ms: number | null;
  p95_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  buckets: { ts: number; count: number; blocked: number }[];
}

export interface RailFrequency {
  name: string;
  count: number;
  blocked: number;
}

export interface MetricSample {
  name: string;
  labels: Record<string, string>;
  ts: number;
  value: number;
}

export interface ChallengeRunResult {
  challenge_id?: string;
  challenge: { id?: string; input?: string; [k: string]: unknown };
  status_code: number;
  response: any;
}
```

- [ ] **Step 4: Write `dashboard/frontend/src/api.ts`**

```ts
import type {
  ChallengeRunResult,
  MetricSample,
  OverviewStats,
  RailFrequency,
  RecordsResponse,
  RequestRecord,
  StatusResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  return search.toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });
}

export const api = {
  status: () => request<StatusResponse>("/api/status"),
  records: (params: Record<string, string | number | undefined>) =>
    request<RecordsResponse>(`/api/requests?${qs(params)}`),
  record: (id: string) => request<RequestRecord>(`/api/requests/${id}`),
  overview: (start?: number, end?: number) =>
    request<OverviewStats>(`/api/metrics/overview?${qs({ start, end })}`),
  rails: () => request<RailFrequency[]>("/api/metrics/rails"),
  series: (namePrefix: string) =>
    request<MetricSample[]>(`/api/metrics/series?${qs({ name_prefix: namePrefix })}`),
  telemetryEvents: () => request<{ items: Record<string, unknown>[] }>("/api/telemetry/events"),
  consoleRun: (body: unknown) => post<unknown>("/api/commands/console/run", body),
  checksRun: (body: unknown) => post<unknown>("/api/commands/checks/run", body),
  challenges: () => request<{ items: Record<string, unknown>[] }>("/api/commands/challenges"),
  runChallenges: (body: unknown) =>
    post<{ results: ChallengeRunResult[] }>("/api/commands/challenges/run", body),
  adminCapabilities: () => request<{ installed: boolean }>("/api/commands/admin/capabilities"),
  adminReload: (configId?: string) =>
    post<unknown>("/api/commands/admin/reload", { config_id: configId }),
};

export function extractSseText(sse: string): string {
  let out = "";
  for (const event of sse.split("\n\n")) {
    for (const line of event.split("\n")) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice("data:".length).trim();
      if (!payload || payload === "[DONE]") continue;
      try {
        const chunk = JSON.parse(payload);
        for (const choice of chunk.choices ?? []) {
          out += choice.delta?.content ?? "";
        }
      } catch {
        // ignore non-JSON keepalives
      }
    }
  }
  return out;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard/frontend && npx vitest run src/api.test.ts`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add dashboard/frontend/src/types.ts dashboard/frontend/src/api.ts dashboard/frontend/src/api.test.ts
git commit -m "feat(dashboard): add typed frontend API client"
```

---

### Task 17: App layout, routing, and shared components

**Files:**
- Modify: `dashboard/frontend/src/App.tsx`
- Create: `dashboard/frontend/src/components.tsx`
- Test: `dashboard/frontend/src/components.test.tsx`

- [ ] **Step 1: Write the failing test (`dashboard/frontend/src/components.test.tsx`)**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JsonBlock, RailBars, StatusPill } from "./components";
import type { RailInfo } from "./types";

describe("StatusPill", () => {
  it("renders the status text", () => {
    render(<StatusPill status="blocked" />);
    expect(screen.getByText("blocked")).toBeTruthy();
  });
});

describe("RailBars", () => {
  const rails: RailInfo[] = [
    { name: "self check input", stop: true, duration: 0.5 },
    { name: "codeword", stop: false, duration: 0.25 },
  ];

  it("renders rail names with stop markers and durations", () => {
    render(<RailBars rails={rails} />);
    expect(screen.getByText("self check input (stopped)")).toBeTruthy();
    expect(screen.getByText("codeword")).toBeTruthy();
    expect(screen.getByText("500 ms")).toBeTruthy();
    expect(screen.getByText("250 ms")).toBeTruthy();
  });

  it("renders empty state", () => {
    render(<RailBars rails={[]} />);
    expect(screen.getByText("No rails activated.")).toBeTruthy();
  });
});

describe("JsonBlock", () => {
  it("pretty-prints JSON", () => {
    render(<JsonBlock data={{ a: 1 }} />);
    expect(screen.getByText(/"a": 1/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard/frontend && npx vitest run src/components.test.tsx`
Expected: FAIL with `Cannot find module './components'`

- [ ] **Step 3: Write `dashboard/frontend/src/components.tsx`**

```tsx
import type { RailInfo } from "./types";

export function StatusPill({ status }: { status: string }) {
  const background =
    status === "blocked" ? "#b3261e" : status === "error" ? "#e8710a" : "#137333";
  return (
    <span
      style={{
        background,
        color: "white",
        borderRadius: 10,
        padding: "2px 10px",
        fontSize: 12,
        textTransform: "uppercase",
      }}
    >
      {status}
    </span>
  );
}

export function SourceTag({ source }: { source: string }) {
  return (
    <span style={{ color: "#5f6368", fontSize: 12, border: "1px solid #dadce0", borderRadius: 4, padding: "1px 6px" }}>
      {source}
    </span>
  );
}

export function JsonBlock({ data }: { data: unknown }) {
  if (data === null || data === undefined) return <em>none</em>;
  return (
    <pre
      style={{
        background: "#f6f8fa",
        border: "1px solid #d0d7de",
        borderRadius: 6,
        padding: 12,
        overflow: "auto",
        maxHeight: 320,
        fontSize: 12,
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export function RailBars({ rails }: { rails: RailInfo[] }) {
  if (!rails.length) return <em>No rails activated.</em>;
  const max = Math.max(0.001, ...rails.map((r) => r.duration ?? 0));
  return (
    <div>
      {rails.map((rail, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ minWidth: 240, fontSize: 13 }}>
            {rail.name}
            {rail.stop ? " (stopped)" : ""}
            {rail.type ? ` [${rail.type}]` : ""}
          </span>
          <div
            style={{
              height: 12,
              background: rail.stop ? "#b3261e" : "#1a73e8",
              borderRadius: 3,
              width: `${Math.max(2, ((rail.duration ?? 0) / max) * 100)}%`,
            }}
          />
          <span style={{ fontSize: 12, color: "#5f6368" }}>
            {rail.duration != null ? `${Math.round(rail.duration * 1000)} ms` : "n/a"}
          </span>
        </div>
      ))}
    </div>
  );
}

export function formatTs(ts: number): string {
  return new Date(ts).toLocaleString();
}

export function formatMs(ms: number | null | undefined): string {
  return ms == null ? "n/a" : `${Math.round(ms)} ms`;
}
```

- [ ] **Step 4: Write `dashboard/frontend/src/App.tsx`**

```tsx
import { NavLink, Route, Routes } from "react-router-dom";
import { HashRouter } from "react-router-dom";

import AdminPage from "./pages/AdminPage";
import ChallengesPage from "./pages/ChallengesPage";
import ConsolePage from "./pages/ConsolePage";
import MetricsPage from "./pages/MetricsPage";
import OverviewPage from "./pages/OverviewPage";
import RequestsPage from "./pages/RequestsPage";
import TelemetryPage from "./pages/TelemetryPage";

const NAV: [string, string][] = [
  ["/", "Overview"],
  ["/requests", "Requests"],
  ["/metrics", "Metrics"],
  ["/telemetry", "Telemetry"],
  ["/console", "Console"],
  ["/challenges", "Challenges"],
  ["/admin", "Admin"],
];

export default function App() {
  return (
    <HashRouter>
      <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif", color: "#202124" }}>
        <nav style={{ width: 190, borderRight: "1px solid #dadce0", padding: "16px 12px", flexShrink: 0 }}>
          <h2 style={{ fontSize: 16, margin: "0 0 16px" }}>Guardrails</h2>
          {NAV.map(([to, label]) => (
            <div key={to} style={{ marginBottom: 6 }}>
              <NavLink
                to={to}
                style={({ isActive }) => ({
                  textDecoration: "none",
                  color: isActive ? "#1a73e8" : "#5f6368",
                  fontWeight: isActive ? 600 : 400,
                })}
              >
                {label}
              </NavLink>
            </div>
          ))}
        </nav>
        <main style={{ flex: 1, padding: 24, overflow: "auto" }}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/requests" element={<RequestsPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/telemetry" element={<TelemetryPage />} />
            <Route path="/console" element={<ConsolePage />} />
            <Route path="/challenges" element={<ChallengesPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Routes>
        </main>
      </div>
    </HashRouter>
  );
}
```

- [ ] **Step 5: Create page stubs so the build passes**

Create each of `dashboard/frontend/src/pages/OverviewPage.tsx`, `RequestsPage.tsx`, `MetricsPage.tsx`, `TelemetryPage.tsx`, `ConsolePage.tsx`, `ChallengesPage.tsx`, `AdminPage.tsx` with this exact content (substituting the name):

```tsx
export default function OverviewPage() {
  return <h1>Overview</h1>;
}
```

Use the matching component name and heading per file (`RequestsPage`, `MetricsPage`, `TelemetryPage`, `ConsolePage`, `ChallengesPage`, `AdminPage`).

- [ ] **Step 6: Run tests and build**

Run: `cd dashboard/frontend && npx vitest run src/components.test.tsx && npm run build`
Expected: 6 passed; build succeeds

- [ ] **Step 7: Commit**

```bash
git add dashboard/frontend/src/App.tsx dashboard/frontend/src/components.tsx dashboard/frontend/src/components.test.tsx dashboard/frontend/src/pages/
git commit -m "feat(dashboard): add app shell, navigation, and shared components"
```

---

### Task 18: Overview page

**Files:**
- Modify: `dashboard/frontend/src/pages/OverviewPage.tsx`

- [ ] **Step 1: Write `dashboard/frontend/src/pages/OverviewPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import { formatMs } from "../components";
import type { OverviewStats, StatusResponse } from "../types";

const RANGES: [string, number][] = [
  ["15 minutes", 15 * 60 * 1000],
  ["1 hour", 60 * 60 * 1000],
  ["24 hours", 24 * 60 * 60 * 1000],
];

export default function OverviewPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [rangeMs, setRangeMs] = useState(RANGES[0][1]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const end = Date.now();
        const [s, o] = await Promise.all([
          api.status(),
          api.overview(end - rangeMs, end),
        ]);
        if (alive) {
          setStatus(s);
          setStats(o);
          setError(null);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [rangeMs]);

  const healthy = status?.guardrails.healthy;
  const chartData = (stats?.buckets ?? []).map((b) => ({
    time: new Date(b.ts).toLocaleTimeString(),
    requests: b.count,
    blocked: b.blocked,
  }));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>Overview</h1>
        <label>
          Range:{" "}
          <select value={rangeMs} onChange={(e) => setRangeMs(Number(e.target.value))}>
            {RANGES.map(([label, ms]) => (
              <option key={label} value={ms}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      {status && (
        <p>
          Guardrails server:{" "}
          <strong style={{ color: healthy ? "#137333" : "#b3261e" }}>
            {healthy ? "healthy" : "unreachable"}
          </strong>{" "}
          ({status.guardrails.url}) — admin hook {status.admin_hook ? "installed" : "not installed"}
        </p>
      )}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
        <StatCard label="Requests" value={stats?.count} />
        <StatCard label="Blocked" value={stats?.blocked} />
        <StatCard label="Errors" value={stats?.errors} />
        <StatCard label="p50 latency" value={formatMs(stats?.p50_ms)} />
        <StatCard label="p95 latency" value={formatMs(stats?.p95_ms)} />
        <StatCard label="Input tokens" value={stats?.input_tokens} />
        <StatCard label="Output tokens" value={stats?.output_tokens} />
      </div>
      <h3>Requests over selected range</h3>
      <div style={{ width: "100%", height: 260 }}>
        <ResponsiveContainer>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Area type="monotone" dataKey="requests" stroke="#1a73e8" fill="#1a73e8" fillOpacity={0.2} />
            <Area type="monotone" dataKey="blocked" stroke="#b3261e" fill="#b3261e" fillOpacity={0.3} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      {status && (
        <>
          <h3>Ingestion</h3>
          <ul>
            <li>Trace globs: {status.ingestion.trace_globs.join(", ") || "none"}</li>
            <li>Prometheus URL: {status.ingestion.prom_url || "none"}</li>
            <li>Records written: {status.ingestion.records_written} (duplicates skipped: {status.ingestion.records_dropped_duplicates})</li>
            <li>
              Malformed lines:{" "}
              {Object.entries(status.ingestion.malformed).length
                ? Object.entries(status.ingestion.malformed)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(", ")
                : "none"}
            </li>
          </ul>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value?: number | string | null }) {
  return (
    <div style={{ border: "1px solid #dadce0", borderRadius: 8, padding: "12px 20px", minWidth: 110 }}>
      <div style={{ fontSize: 12, color: "#5f6368" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 600 }}>{value ?? "n/a"}</div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check and build**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/OverviewPage.tsx
git commit -m "feat(dashboard): add overview page with stats and chart"
```

---

### Task 19: Requests page with detail view

**Files:**
- Modify: `dashboard/frontend/src/pages/RequestsPage.tsx`
- Create: `dashboard/frontend/src/pages/RequestDetail.tsx`

- [ ] **Step 1: Write `dashboard/frontend/src/pages/RequestDetail.tsx`**

```tsx
import { JsonBlock, RailBars, SourceTag, StatusPill, formatTs } from "../components";
import type { RequestRecord } from "../types";

export default function RequestDetail({ record }: { record: RequestRecord }) {
  return (
    <div style={{ border: "1px solid #dadce0", borderRadius: 8, padding: 16, marginTop: 16 }}>
      <h3 style={{ marginTop: 0 }}>
        Request detail <StatusPill status={record.status} /> <SourceTag source={record.source} />
      </h3>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        {formatTs(record.ts)} — config: {record.config_id ?? "n/a"} — thread: {record.thread_id ?? "n/a"}
        {record.interaction_id ? ` — interaction: ${record.interaction_id}` : ""}
      </p>
      {record.error && <p style={{ color: "#b3261e" }}>Error: {record.error}</p>}
      <h4>Activated rails</h4>
      <RailBars rails={record.rails} />
      <h4>LLM calls</h4>
      {record.llm_calls.length ? (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #dadce0" }}>
              <th>Task</th><th>Model</th><th>Prompt tok</th><th>Completion tok</th><th>Total</th><th>Duration</th><th>Cache</th>
            </tr>
          </thead>
          <tbody>
            {record.llm_calls.map((c, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                <td>{c.task ?? ""}</td>
                <td>{c.model ?? "unknown"}</td>
                <td>{c.prompt_tokens ?? ""}</td>
                <td>{c.completion_tokens ?? ""}</td>
                <td>{c.total_tokens ?? ""}</td>
                <td>{c.duration != null ? `${Math.round(c.duration * 1000)} ms` : ""}</td>
                <td>{c.from_cache ? "hit" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <em>No LLM calls captured.</em>
      )}
      {Object.keys(record.phase_durations).length > 0 && (
        <>
          <h4>Phase durations</h4>
          <ul>
            {Object.entries(record.phase_durations).map(([k, v]) => (
              <li key={k}>
                {k}: {typeof v === "number" && v < 1000 ? `${Math.round(v * 1000)} ms` : String(v)}
              </li>
            ))}
          </ul>
        </>
      )}
      <h4>Raw request</h4>
      <JsonBlock data={record.raw_request} />
      <h4>Raw response</h4>
      <JsonBlock data={record.raw_response} />
    </div>
  );
}
```

- [ ] **Step 2: Write `dashboard/frontend/src/pages/RequestsPage.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { SourceTag, StatusPill, formatTs } from "../components";
import type { RecordsResponse } from "../types";
import RequestDetail from "./RequestDetail";

const PAGE_SIZE = 50;
const RANGES: [string, number][] = [
  ["all time", 0],
  ["15 minutes", 15 * 60 * 1000],
  ["1 hour", 60 * 60 * 1000],
  ["24 hours", 24 * 60 * 60 * 1000],
];

export default function RequestsPage() {
  const [filters, setFilters] = useState({ status: "", source: "", search: "", configId: "", rail: "" });
  const [rangeMs, setRangeMs] = useState(RANGES[1][1]);
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [data, setData] = useState<RecordsResponse>({ items: [], total: 0 });
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<RecordsResponse["items"][0] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s) => setConfigs(s.guardrails.configs ?? []))
      .catch(() => setConfigs([]));
  }, []);

  const load = useCallback(async () => {
    try {
      const end = Date.now();
      const result = await api.records({
        status: filters.status || undefined,
        source: filters.source || undefined,
        search: filters.search || undefined,
        config_id: filters.configId || undefined,
        rail: filters.rail || undefined,
        start: rangeMs > 0 ? end - rangeMs : undefined,
        end: rangeMs > 0 ? end : undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setData(result);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [filters, rangeMs, offset]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    api
      .record(selectedId)
      .then(setSelected)
      .catch((e) => setError((e as Error).message));
  }, [selectedId]);

  const update = (patch: Partial<typeof filters>) => {
    setOffset(0);
    setFilters((f) => ({ ...f, ...patch }));
  };

  return (
    <div>
      <h1>Requests</h1>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        <select value={rangeMs} onChange={(e) => { setOffset(0); setRangeMs(Number(e.target.value)); }}>
          {RANGES.map(([label, ms]) => (
            <option key={label} value={ms}>
              {label}
            </option>
          ))}
        </select>
        <select value={filters.configId} onChange={(e) => update({ configId: e.target.value })}>
          <option value="">any config</option>
          {configs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id}
            </option>
          ))}
        </select>
        <input
          placeholder="rail name..."
          value={filters.rail}
          onChange={(e) => update({ rail: e.target.value })}
          style={{ width: 140 }}
        />
        <select value={filters.status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">any status</option>
          <option value="allowed">allowed</option>
          <option value="blocked">blocked</option>
          <option value="error">error</option>
        </select>
        <select value={filters.source} onChange={(e) => update({ source: e.target.value })}>
          <option value="">any source</option>
          <option value="proxy">proxy</option>
          <option value="trace_file">trace_file</option>
          <option value="console">console</option>
          <option value="check">check</option>
          <option value="challenge">challenge</option>
        </select>
        <input
          placeholder="search input/output..."
          value={filters.search}
          onChange={(e) => update({ search: e.target.value })}
          style={{ flex: 1 }}
        />
        <button onClick={load}>Refresh</button>
      </div>
      <p style={{ fontSize: 13, color: "#5f6368" }}>{data.total} records</p>
      <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "2px solid #dadce0" }}>
            <th>Time</th><th>Source</th><th>Config</th><th>Status</th><th>Input</th><th>Output</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((r) => (
            <tr
              key={r.id}
              onClick={() => setSelectedId(r.id)}
              style={{
                borderBottom: "1px solid #eee",
                cursor: "pointer",
                background: r.id === selectedId ? "#e8f0fe" : undefined,
              }}
            >
              <td style={{ whiteSpace: "nowrap" }}>{formatTs(r.ts)}</td>
              <td><SourceTag source={r.source} /></td>
              <td>{r.config_id ?? ""}</td>
              <td><StatusPill status={r.status} /></td>
              <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.input_summary}
              </td>
              <td style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.output_summary}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </button>
        <button
          disabled={offset + PAGE_SIZE >= data.total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </button>
      </div>
      {selected && <RequestDetail record={selected} />}
    </div>
  );
}
```

- [ ] **Step 3: Type-check and build**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/pages/RequestsPage.tsx dashboard/frontend/src/pages/RequestDetail.tsx
git commit -m "feat(dashboard): add requests list and detail pages"
```

---

### Task 20: Metrics page (Prometheus time series)

**Files:**
- Modify: `dashboard/frontend/src/pages/MetricsPage.tsx`

- [ ] **Step 1: Write `dashboard/frontend/src/pages/MetricsPage.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api";
import type { MetricSample } from "../types";

export default function MetricsPage() {
  const [samples, setSamples] = useState<MetricSample[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await api.series("guardrails_nonstream");
        if (alive) {
          setSamples(data);
          setError(null);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  // one series per (metric name + label signature)
  const series = useMemo(() => {
    const groups = new Map<string, MetricSample[]>();
    for (const s of samples) {
      const labelSig = Object.entries(s.labels)
        .map(([k, v]) => `${k}=${v}`)
        .join(",");
      const key = labelSig ? `${s.name}{${labelSig}}` : s.name;
      const list = groups.get(key) ?? [];
      list.push(s);
      groups.set(key, list);
    }
    return [...groups.entries()].map(([name, points]) => ({
      name,
      points: points.map((p) => ({ time: new Date(p.ts).toLocaleTimeString(), value: p.value })),
    }));
  }, [samples]);

  return (
    <div>
      <h1>Metrics</h1>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        Time series scraped from the guardrails Prometheus exporter. Shows the
        exported admission-queue instruments (refreshes every 5 seconds).
      </p>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      {!error && samples.length === 0 && (
        <em>
          No samples yet. Start the dashboard with --prom-url pointing at the
          guardrails metrics exporter and generate some traffic.
        </em>
      )}
      {series.map((s) => (
        <div key={s.name} style={{ marginBottom: 32 }}>
          <h3 style={{ fontSize: 14 }}>{s.name}</h3>
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={s.points}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" />
                <YAxis allowDecimals={false} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" dot={false} stroke="#1a73e8" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check and build**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/MetricsPage.tsx
git commit -m "feat(dashboard): add prometheus metrics page"
```

---

### Task 21: Telemetry page (usage stats events)

**Files:**
- Modify: `dashboard/frontend/src/pages/TelemetryPage.tsx`

- [ ] **Step 1: Write `dashboard/frontend/src/pages/TelemetryPage.tsx`**

```tsx
import { useEffect, useState } from "react";

import { api } from "../api";

const COLUMNS = [
  "event",
  "timestamp",
  "sessionId",
  "nemoguardrailsVersion",
  "railsEngine",
  "deploymentType",
  "numRailsConfigured",
  "numCustomFlows",
  "tracingEnabled",
  "streamingConfigured",
];

export default function TelemetryPage() {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .telemetryEvents()
      .then((d) => setEvents(d.items))
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <h1>Telemetry</h1>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        Anonymous usage events from the local audit file
        (~/.config/nemoguardrails/usage_stats.json). Read-only; newest last.
      </p>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      {events.length === 0 && !error && <em>No telemetry events found.</em>}
      {events.length > 0 && (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "2px solid #dadce0" }}>
              {COLUMNS.map((c) => (
                <th key={c}>{c}</th>
              ))}
              <th>railTypesInUse</th>
              <th>llmProviders</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                {COLUMNS.map((c) => (
                  <td key={c}>
                    {c === "timestamp"
                      ? e[c] != null
                        ? new Date(Number(e[c]) * 1000).toLocaleString()
                        : ""
                      : String(e[c] ?? "")}
                  </td>
                ))}
                <td>{Array.isArray(e.railTypesInUse) ? (e.railTypesInUse as string[]).join(", ") : ""}</td>
                <td>{Array.isArray(e.llmProviders) ? (e.llmProviders as string[]).join(", ") : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check and build**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/TelemetryPage.tsx
git commit -m "feat(dashboard): add usage telemetry page"
```

---

### Task 22: Console page (test prompts)

**Files:**
- Modify: `dashboard/frontend/src/pages/ConsolePage.tsx`

- [ ] **Step 1: Write `dashboard/frontend/src/pages/ConsolePage.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";

import { api, extractSseText } from "../api";
import { RailBars } from "../components";
import type { StatusResponse } from "../types";

interface ConsoleResult {
  output: string;
  log?: {
    activated_rails?: { name?: string; stop?: boolean; duration?: number; type?: string }[];
    stats?: Record<string, number>;
  };
  raw: unknown;
}

export default function ConsolePage() {
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [configId, setConfigId] = useState("");
  const [system, setSystem] = useState("");
  const [prompt, setPrompt] = useState("");
  const [useStream, setUseStream] = useState(false);
  const [result, setResult] = useState<ConsoleResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .status()
      .then((s: StatusResponse) => {
        setConfigs(s.guardrails.configs ?? []);
        if (s.guardrails.configs?.length) setConfigId(s.guardrails.configs[0].id);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const run = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    const messages = [
      ...(system.trim() ? [{ role: "system", content: system }] : []),
      { role: "user", content: prompt },
    ];
    const body = { config_id: configId || undefined, messages };
    try {
      if (useStream) {
        abortRef.current = new AbortController();
        const resp = await fetch("/api/commands/console/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, stream: true }),
          signal: abortRef.current.signal,
        });
        if (!resp.ok || !resp.body) throw new Error(await resp.text());
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          setResult({
            output: extractSseText(buffer),
            log: undefined,
            raw: { streamed: true },
          });
        }
      } else {
        const data: any = await api.consoleRun(body);
        const log = data?.guardrails?.log;
        setResult({
          output: data?.choices?.[0]?.message?.content ?? JSON.stringify(data),
          log,
          raw: data,
        });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <h1>Console</h1>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        Send a test prompt through the recording pipeline. Every run is stored
        as a request record (source=console) and appears on the Requests page.
      </p>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <label>
          Config:{" "}
          <select value={configId} onChange={(e) => setConfigId(e.target.value)}>
            <option value="">(default)</option>
            {configs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={useStream} onChange={(e) => setUseStream(e.target.checked)} />{" "}
          stream
        </label>
      </div>
      <input
        placeholder="System prompt (optional)"
        value={system}
        onChange={(e) => setSystem(e.target.value)}
        style={{ width: "100%", marginBottom: 8 }}
      />
      <textarea
        placeholder="User message..."
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={4}
        style={{ width: "100%", marginBottom: 8 }}
      />
      <button onClick={run} disabled={running || !prompt.trim()}>
        {running ? "Running..." : "Send"}
      </button>
      {result && (
        <div style={{ marginTop: 16 }}>
          <h3>Response</h3>
          <pre style={{ background: "#f6f8fa", padding: 12, borderRadius: 6, whiteSpace: "pre-wrap" }}>
            {result.output}
          </pre>
          {result.log && (
            <>
              <h4>Activated rails</h4>
              <RailBars rails={result.log.activated_rails ?? []} />
              {result.log.stats && (
                <>
                  <h4>Stats</h4>
                  <ul>
                    {Object.entries(result.log.stats).map(([k, v]) => (
                      <li key={k}>
                        {k}: {typeof v === "number" && v < 10000 ? `${Math.round(v * 1000)} ms` : String(v)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check and build**

Run: `cd dashboard/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add dashboard/frontend/src/pages/ConsolePage.tsx
git commit -m "feat(dashboard): add test prompt console page"
```

---

### Task 23: Challenges and Admin pages

**Files:**
- Modify: `dashboard/frontend/src/pages/ChallengesPage.tsx`
- Modify: `dashboard/frontend/src/pages/AdminPage.tsx`

- [ ] **Step 1: Write `dashboard/frontend/src/pages/ChallengesPage.tsx`**

```tsx
import { useEffect, useState } from "react";

import { api } from "../api";
import { JsonBlock, StatusPill } from "../components";
import type { ChallengeRunResult, StatusResponse } from "../types";

export default function ChallengesPage() {
  const [configs, setConfigs] = useState<{ id: string }[]>([]);
  const [configId, setConfigId] = useState("");
  const [challenges, setChallenges] = useState<Record<string, unknown>[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [results, setResults] = useState<ChallengeRunResult[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.status(), api.challenges()])
      .then(([s, c]) => {
        setConfigs(s.guardrails.configs ?? []);
        if (s.guardrails.configs?.length) setConfigId(s.guardrails.configs[0].id);
        setChallenges(c.items);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const toggle = (i: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const ids = [...selected].map((i) => challenges[i]).map((c: any) => c.id).filter(Boolean);
      const data = await api.runChallenges({ config_id: configId || undefined, challenge_ids: ids });
      setResults(data.results);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const wasBlocked = (r: ChallengeRunResult) =>
    Boolean(r.response?.guardrails?.log?.activated_rails?.some((rail: any) => rail.stop));

  return (
    <div>
      <h1>Challenges</h1>
      <p style={{ fontSize: 13, color: "#5f6368" }}>
        Red-teaming challenge prompts served by the guardrails server
        (/v1/challenges). Runs are recorded with source=challenge.
      </p>
      {error && <p style={{ color: "#b3261e" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <label>
          Config:{" "}
          <select value={configId} onChange={(e) => setConfigId(e.target.value)}>
            <option value="">(default)</option>
            {configs.map((c) => (
              <option key={c.id} value={c.id}>
                {c.id}
              </option>
            ))}
          </select>
        </label>
        <button onClick={run} disabled={running}>
          {running ? "Running..." : `Run selected (${selected.size || "all"})`}
        </button>
      </div>
      {challenges.map((c: any, i) => (
        <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4, fontSize: 13 }}>
          <input type="checkbox" checked={selected.has(i)} onChange={() => toggle(i)} />
          <span style={{ color: "#5f6368", minWidth: 60 }}>{c.id ?? `#${i}`}</span>
          <span>{c.input ?? c.prompt ?? JSON.stringify(c)}</span>
        </div>
      ))}
      {results.map((r, i) => (
        <div key={i} style={{ border: "1px solid #dadce0", borderRadius: 8, padding: 12, marginTop: 12 }}>
          <h4 style={{ margin: 0 }}>
            {r.challenge_id ?? `challenge ${i}`}{" "}
            <StatusPill status={r.status_code === 200 ? (wasBlocked(r) ? "blocked" : "allowed") : "error"} />
          </h4>
          <p style={{ fontSize: 13 }}>{r.challenge?.input ?? ""}</p>
          <JsonBlock data={r.response} />
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Write `dashboard/frontend/src/pages/AdminPage.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { JsonBlock } from "../components";
import type { StatusResponse } from "../types";

const HOOK_INSTRUCTIONS = `The guardrails server does not have the admin hook installed.

To enable config reload, copy dashboard/admin_hook/guardrails_admin.py into
your guardrails config folder and wire it from that folder's config.py:

  import importlib.util
  import os

  def _load_admin_hook(app):
      path = os.path.join(os.path.dirname(__file__), "guardrails_admin.py")
      spec = importlib.util.spec_from_file_location("guardrails_admin", path)
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      module.init(app)

  def init(app):
      _load_admin_hook(app)

Then restart the guardrails server.`;

export default function AdminPage() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [configId, setConfigId] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .status()
      .then((s) => {
        setStatus(s);
        setError(null);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(load, [load]);

  const reload = async () => {
    setMessage(null);
    setError(null);
    try {
      const result: any = await api.adminReload(configId || undefined);
      setMessage(`Reloaded: ${JSON.stringify(result)}`);
      setTimeout(load, 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const configs = status?.guardrails.configs ?? [];

  return (
    <div>
      <h1>Admin</h1>
      {error && <p style={{ color: "#b3261e", whiteSpace: "pre-wrap" }}>{error}</p>}
      {message && <p style={{ color: "#137333" }}>{message}</p>}
      <h3>Server</h3>
      {status && (
        <ul>
          <li>
            Health:{" "}
            <strong style={{ color: status.guardrails.healthy ? "#137333" : "#b3261e" }}>
              {status.guardrails.healthy ? "healthy" : "unreachable"}
            </strong>{" "}
            ({status.guardrails.url})
          </li>
          <li>Admin hook: {status.admin_hook ? "installed" : "not installed"}</li>
        </ul>
      )}
      <h3>Configs</h3>
      {configs.length === 0 && <em>No configs reported (server unreachable or none loaded).</em>}
      <ul>
        {configs.map((c) => (
          <li key={c.id}>{c.id}</li>
        ))}
      </ul>
      <h3>Models</h3>
      <JsonBlock data={status?.guardrails.models ?? null} />
      <h3>Reload config</h3>
      {status && !status.admin_hook && (
        <pre style={{ background: "#fef7e0", border: "1px solid #f9ab00", borderRadius: 6, padding: 12, fontSize: 12, whiteSpace: "pre-wrap" }}>
          {HOOK_INSTRUCTIONS}
        </pre>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <select value={configId} onChange={(e) => setConfigId(e.target.value)}>
          <option value="">all configs</option>
          {configs.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id}
            </option>
          ))}
        </select>
        <button onClick={reload} disabled={!status?.admin_hook}>
          Reload
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Type-check, run all frontend tests, and build**

Run: `cd dashboard/frontend && npm run build && npx vitest run`
Expected: build succeeds; all tests pass (3 api + 6 components = 9)

- [ ] **Step 4: Commit**

```bash
git add dashboard/frontend/src/pages/ChallengesPage.tsx dashboard/frontend/src/pages/AdminPage.tsx
git commit -m "feat(dashboard): add challenges and admin pages"
```

---

### Task 24: Full verification and final wiring

**Files:**
- Modify: none (verification task)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard && uv run pytest -v`
Expected: all tests pass

- [ ] **Step 2: Build the frontend**

Run: `cd dashboard/frontend && npm run build`
Expected: `tsc --noEmit` and `vite build` succeed; `dist/` contains `index.html`

- [ ] **Step 3: Smoke-test the running dashboard end to end**

Run a mock guardrails server and the dashboard together:

```bash
# terminal 1: minimal mock of the guardrails server
cd dashboard && uv run python - <<'EOF'
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

@app.get("/v1/health")
async def health():
    return {"status": "pass"}

@app.get("/v1/rails/configs")
async def configs():
    return [{"id": "demo"}]

@app.get("/v1/models")
async def models():
    return {"data": [{"id": "mock-model"}]}

@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    return JSONResponse({
        "choices": [{"message": {"role": "assistant", "content": "mock reply"}, "finish_reason": "stop"}],
        "guardrails": {
            "config_id": body.get("guardrails", {}).get("config_id"),
            "log": {
                "activated_rails": [{"type": "input", "name": "self check input", "decisions": [], "stop": False, "duration": 0.05}],
                "stats": {"total_duration": 0.1, "llm_calls_duration": 0.08, "llm_calls_count": 1},
                "llm_calls": [{"task": "self check input", "duration": 0.08, "prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15, "llm_model_name": "mock-model", "llm_provider_name": "mock"}],
            },
        },
    })

uvicorn.run(app, host="127.0.0.1", port=8000)
EOF
```

```bash
# terminal 2: the dashboard
cd dashboard && uv run python -m backend.main --guardrails-url http://127.0.0.1:8000 --port 8500 --db /tmp/dash-smoke.db
```

Then verify (in a third shell):

```bash
# the dashboard reports the mock server as healthy
curl -s localhost:8500/api/status | python -c "import sys,json; d=json.load(sys.stdin); assert d['guardrails']['healthy'], d; print('status ok')"

# a proxied chat is recorded
curl -s -X POST localhost:8500/proxy/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"hello"}],"guardrails":{"config_id":"demo"}}' >/dev/null
curl -s 'localhost:8500/api/requests?source=proxy' | python -c "import sys,json; d=json.load(sys.stdin); assert d['total']==1, d; assert d['items'][0]['rails'][0]['name']=='self check input'; print('proxy recording ok')"

# the SPA is served
curl -s localhost:8500/ | grep -q 'id="root"' && echo "static ok"

# the console command records with source=console
curl -s -X POST localhost:8500/api/commands/console/run \
  -H 'Content-Type: application/json' \
  -d '{"config_id":"demo","messages":[{"role":"user","content":"hi"}]}' >/dev/null
curl -s 'localhost:8500/api/requests?source=console' | python -c "import sys,json; d=json.load(sys.stdin); assert d['total']==1, d; print('console ok')"
```

Expected: all four checks print ok. Then stop both servers and clean up: `rm -f /tmp/dash-smoke.db*`.

- [ ] **Step 4: Run pre-commit on all new dashboard files**

Run: `cd /home/andrewh/code/personal/Guardrails && uv run --locked pre-commit run --files $(git diff --name-only HEAD -- | grep '^dashboard/' | tr '\n' ' ')`
Expected: passes (or report any skipped hooks clearly, per repository rules). If Ruff flags unused imports in `backend/api/commands.py` (the `import json` / `import httpx` placement), fix by moving them to the top of the file and re-run.

- [ ] **Step 5: Final commit (only if Step 4 produced fixes)**

```bash
git add -A dashboard/
git commit -m "chore(dashboard): lint fixes from pre-commit"
```

If nothing changed in Step 4, skip this commit.

---

## Self-Review Notes

Checked against the spec after writing:

- **Spec coverage:** all four collectors (proxy Tasks 6-7, traces Task 8, prometheus Task 9, usage telemetry Task 10), all four data sources (per-request logs/traces, metrics aggregates, server status/config, usage telemetry), all four command groups (console/checks Task 12, config/model management Tasks 11-12, challenge runner Task 12, reload via hook Tasks 12+14), all seven UI pages (Tasks 18-23), error handling (502/409 paths tested in Tasks 6 and 12), testing strategy (backend pytest Tasks 2-13, frontend vitest Tasks 16-17, build gates each frontend task, end-to-end smoke test Task 24). Spec's "user review gate" items are all covered.
- **Type consistency:** `RequestRecord` fields, `Database` method names (`insert_record`, `list_records`, `get_record`, `metric_series`, `metric_names`, `insert_samples`, `get_state`, `set_state`, `increment_state`), `RecordWriter` (`start`, `enqueue`, `stop`, `written`, `dropped`, `_queue`), `TraceIngester` (`scan_once`, `run_forever`), `parse_prometheus_text`, `scrape_prometheus_once`, `prometheus_loop`, `forward_chat`, `record_from_chat`, `record_from_stream`, `record_from_trace_line`, `read_usage_events`, `overview_stats`, `rails_frequency`, `build_settings`, `create_app`, and the API surface used by `frontend/src/api.ts` are identical across all tasks.
- **Placeholder scan:** no TBD/TODO steps; every code step is complete.
