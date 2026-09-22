# Guardrails Admin Dashboard — Design

Date: 2026-09-22
Status: Approved (pending spec review)

## Summary

A standalone web dashboard for the NeMo Guardrails server. It collects the data
that Guardrails produces at runtime (per-request generation logs, trace files,
Prometheus metrics, anonymous usage telemetry), displays it in a browser UI, and
lets the operator issue API commands to a running guardrails server: test
prompts, guardrail checks, red-teaming challenges, and config reload.

## Goals and Non-Goals

Goals:

- Record and display every request that flows through the guardrails server
  (activated rails, decisions, phase durations, LLM calls, token usage).
- Display server status, loaded configs, available models, and health.
- Display metrics time series (from the opt-in Prometheus exporter) and usage
  telemetry events.
- Provide a test console, a challenge runner, and config reload.
- Run locally as a single-user tool with no authentication.

Non-goals:

- No changes to `nemoguardrails/` core. The one server-side integration is an
  optional, self-contained hook file the user opts into.
- No multi-user support, RBAC, SSO, or TLS termination.
- Not a contribution-ready feature of the library; it is a standalone tool
  co-located in this repository.

## Key Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Placement | Top-level `dashboard/` directory with its own uv project | Standalone in spirit; keeps library deps and lockfile untouched |
| Collection | Both: recording proxy + file/metrics ingestion, auto-detected | Proxy guarantees full capture; ingestion works for existing traffic and servers |
| Stack | FastAPI backend + React SPA (Vite + TypeScript) | Requested; SPA served as static files by FastAPI, no separate web server |
| Persistence | SQLite (WAL) via stdlib `sqlite3` | Zero new heavy deps; survives restarts; supports time-range aggregates |
| Commands | Console, config/model management, challenge runner, reload | Full requested surface |
| Deployment | Local single-user, localhost, no auth | Requested scope |

## Background: What the Guardrails Server Exposes Today

`nemoguardrails server` (FastAPI, `nemoguardrails/server/api.py`) provides:

- `GET /v1/rails/configs`, `GET /v1/models`, `GET /v1/health`, `GET /v1/challenges`
- `POST /v1/chat/completions` (OpenAI-compatible, SSE streaming supported)
- `POST /v1/checks`
- A config folder's `config.py` may define `init(app)` / `register_datastore(...)`
  / `register_logger(...)` to extend the app.
- Prometheus metrics export is opt-in
  (`NEMO_GUARDRAILS_SERVER_METRICS_EXPORTER=prometheus`, default port 9464) and
  currently exports only the `guardrails.nonstream.*` admission-queue instruments.
- Per-request `GenerationLog` (activated rails, per-phase durations, LLM calls,
  token counts) is returned when the request sets
  `guardrails.options.log.activated_rails` / `llm_calls` / etc.
- Traces can be written as JSONL via the FileSystem tracing adapter
  (default `./.traces/trace.jsonl`); anonymous usage telemetry keeps a local
  JSONL audit copy at `~/.config/nemoguardrails/usage_stats.json`.
- There is **no** reload/introspection endpoint; `--auto-reload` uses a watchdog
  that invalidates entries in the server's `llm_rails_instances` cache.

## Architecture

```
dashboard/
├── pyproject.toml            # standalone uv project
├── README.md                 # run instructions + admin hook install
├── backend/
│   ├── main.py               # FastAPI app factory; uvicorn entrypoint
│   ├── settings.py           # pydantic-settings
│   ├── db.py                 # sqlite (WAL), schema, async write queue
│   ├── models.py             # RequestRecord — normalized per-request row
│   ├── proxy.py              # recording proxy for chat completions + checks
│   ├── ingest.py             # background collectors (traces, prometheus)
│   ├── guardrails_client.py  # typed client for server APIs
│   └── api/
│       ├── status.py         # health, configs, models, ingestion state
│       ├── requests.py       # list/get/search RequestRecords
│       ├── metrics.py        # aggregates from sqlite + prometheus passthrough
│       ├── telemetry.py      # usage stats events
│       └── commands.py       # console run, checks, challenges, reload
├── admin_hook/
│   └── guardrails_admin.py   # optional drop-in for a config folder's config.py
└── frontend/                 # Vite + React + TypeScript SPA
```

`backend/main.py` CLI arguments / settings:

- `--port` (dashboard listen port)
- `--guardrails-url` (base URL of the guardrails server)
- `--db` (sqlite path, default `~/.nemoguardrails/dashboard/dashboard.db`)
- `--trace-glob` (repeatable, e.g. `<app>/.traces/*.jsonl`)
- `--prom-url` (e.g. `http://localhost:9464/metrics`)
- `--scrape-interval` (seconds, default 15)

## Data Model

Single normalized table `request_records` — the only query surface the UI needs:

- `id` (uuid), `ts` (epoch ms), `source` (`proxy` | `trace_file` | `challenge`)
- `interaction_id` (dedupe key across sources), `config_id`, `thread_id`
- `input_summary`, `output_summary` (truncated text for list views)
- `status` (`allowed` | `blocked` | `error`)
- `rails` (JSON: name, type, duration, stop flag per activated rail)
- `llm_calls` (JSON: provider, model, input/output/total tokens, latency)
- `phase_durations` (JSON: input/dialog/generation/output/total)
- `error` (text, nullable)
- `raw_request`, `raw_response` (JSON text, nullable)

Supporting tables:

- `metric_samples` (`name`, `labels_json`, `ts`, `value`) — Prometheus scrapes.
- `ingest_state` (per-file byte offsets, last scrape ts, malformed-line counts).

Aggregates (blocked rate, p50/p95 latency, token sums, most-activated rails) are
computed with SQL over `request_records`, so the Overview page works even when
the Prometheus exporter is disabled.

## Data Flow

### 1. Recording proxy (`proxy.py`)

- Exposes `POST /proxy/v1/chat/completions` and `POST /proxy/v1/checks`,
  OpenAI-compatible, so clients can repoint their base URL at the dashboard.
- Injects `guardrails.options.log` (activated rails, LLM calls, stats) unless
  the caller already set it.
- Non-streaming: parses the upstream response, extracts `guardrails.log`,
  writes a `RequestRecord`, returns the response body unchanged.
- Streaming (`stream=true`): SSE chunks pass through to the client as they
  arrive while being tee-d; on `[DONE]` the completion is assembled and
  recorded. Mid-stream errors pass through to the client; the record write is
  skipped.
- Upstream failures (connection refused, non-2xx) are returned to the caller
  with the original status and body.

### 2. Trace file ingestion (`ingest.py`)

- Background task tails each configured glob using per-file byte offsets from
  `ingest_state`; rotation or truncation is detected by size/inode change and
  resets the offset.
- Each `InteractionLog` JSONL line is normalized into a `RequestRecord`
  (source=`trace_file`), deduped by `interaction_id` so proxy and file
  ingestion of the same traffic never double-count. Dedupe applies only when
  both records carry the same non-null `interaction_id`; proxy records may lack
  one, in which case they are always inserted.
- Malformed lines are skipped, counted in `ingest_state`, and surfaced on the
  status endpoint.

### 3. Prometheus scraping (`ingest.py`)

- Background task scrapes `--prom-url` every `--scrape-interval` seconds,
  parses the text exposition format, and appends to `metric_samples`.
- Powers the Metrics page time series; the latest scrape is also passed through
  live for current-value reads.

### 4. Usage telemetry (`telemetry.py`)

- Reads `~/.config/nemoguardrails/usage_stats.json` (JSONL, respects the 10 MB
  rotation by reading only the current file), exposes events read-only. The
  dashboard never emits telemetry of its own.

### 5. Server status (`guardrails_client.py`)

- Polls `/v1/health`, `/v1/rails/configs`, `/v1/models` on demand and on a
  short interval for the Overview health pill.

## Admin Hook and Reload

`admin_hook/guardrails_admin.py` is a self-contained snippet the user imports
from their guardrails config folder's `config.py` (the existing `init(app)`
mechanism in `nemoguardrails/server/api.py`). It registers:

- `GET /v1/admin/capabilities` — marker endpoint the dashboard probes to detect
  the hook.
- `POST /v1/admin/reload` — drops the named config (or all configs) from the
  server's `llm_rails_instances` cache, forcing a rebuild on the next request —
  the same mechanism `--auto-reload` uses.

If the capabilities probe fails, the dashboard's Reload button renders install
instructions for the hook instead of failing.

## UI Pages (React SPA)

- **Overview** — health pill, request count, blocked rate, p50/p95 latency,
  token totals with a time-range selector; sparklines from the aggregates API;
  ingestion status (proxy active, last trace read, last scrape, malformed-line
  counts).
- **Requests** — filterable table (time range, config, status, rail, source,
  text search over input/output). Row expands into a detail view: activated
  rails timeline with durations, LLM call list, phase breakdown, full
  generation log JSON, raw request/response bodies.
- **Metrics** — time series from `metric_samples` (queue depth, rejections,
  and any other exported series) with live refresh.
- **Telemetry** — usage-stats events table (event type, timestamps, rail
  counts, versions).
- **Console** — test-prompt form: config selector, thread ID, context JSON,
  streaming toggle. Sends through the recording proxy so every test is itself
  captured; renders the reply plus the generation-log breakdown.
- **Challenges** — fetches `/v1/challenges`, runs one or all against the
  selected config, shows blocked/allowed per challenge. Challenge runs are sent
  through the recording proxy and written with `source=challenge`.
- **Admin** — config list, models list, health, and the Reload button.

The Vite build output is served by FastAPI as static files; in development the
SPA dev server proxies `/api` and `/proxy` to the backend.

## Error Handling

- Guardrails server unreachable: red banner in the UI; collectors retry with
  exponential backoff; stored data remains browsable.
- Proxy upstream failure: original status and body returned to the caller.
- Trace parse errors: skip-and-count, surfaced in ingestion status.
- SQLite: single writer through an asyncio queue, WAL mode — reads never block
  writes.
- Reload without the hook: actionable install hint, not a stack trace.

## Testing

- Backend pytest with the guardrails server mocked via respx/httpx: proxy
  recording (non-streaming and SSE pass-through), trace ingestion fixtures
  (including malformed lines and rotation), aggregate queries, telemetry
  parsing. No live LLM or provider calls (per repository policy).
- Frontend: vitest + React Testing Library for the table, detail, and console
  components; `npm run build` must pass as the build gate.
- Pre-commit covers the new Python code per repository rules.

## Open Questions

None — all clarifying decisions were made during brainstorming and are recorded
in Key Decisions above.
