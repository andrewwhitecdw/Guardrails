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
