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
import glob
import json
import os
import re
import time

import httpx

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
            try:
                await self.scan_once()
            except Exception:
                # A bad scan must not kill the collector; retry next interval.
                pass
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
            st = os.stat(path)
        except OSError:
            return
        state_key = f"trace:{path}"
        malformed_key = f"malformed:{path}"
        offset = 0
        prev_mtime = None
        raw = self._db.get_state(state_key)
        if raw:
            try:
                prev_mtime_str, offset_str = raw.split(":", 1)
                prev_mtime = int(prev_mtime_str)
                offset = int(offset_str)
            except ValueError:
                offset = 0
        # Rotated, truncated, or rewritten in place: the mtime moved but the
        # file did not grow past the remembered offset.
        if prev_mtime is not None and st.st_mtime_ns != prev_mtime and st.st_size <= offset:
            offset = 0
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read()
            # Hold back a trailing partial line: the adapter may be mid-append.
            complete, _, pending = data.rpartition(b"\n")
            self._db.set_state(state_key, f"{st.st_mtime_ns}:{offset + len(data) - len(pending)}")
            if not complete:
                return
            mtime_ms = st.st_mtime_ns // 1_000_000
            for raw_line in complete.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    self._db.increment_state(malformed_key)
                    continue
                if not isinstance(entry, dict):
                    self._db.increment_state(malformed_key)
                    continue
                try:
                    record = record_from_trace_line(entry, ts_ms=mtime_ms)
                except (AttributeError, TypeError):
                    self._db.increment_state(malformed_key)
                    continue
                await self._writer.enqueue(record)
        except OSError:
            return


def now_ms() -> int:
    return int(time.time() * 1000)


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
    samples = [(name, json.dumps(labels), ts, value) for name, labels, value in parse_prometheus_text(resp.text)]
    db.insert_samples(samples)


async def prometheus_loop(db: Database, http: httpx.AsyncClient, prom_url: str, interval: float):
    while True:
        try:
            await scrape_prometheus_once(db, http, prom_url)
        except Exception:
            # A failed scrape must not kill the collector; retry next interval.
            pass
        await asyncio.sleep(interval)
