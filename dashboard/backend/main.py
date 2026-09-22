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
            tasks.append(asyncio.create_task(prometheus_loop(db, http, settings.prom_url, settings.scrape_interval)))
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
