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
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
        self._db.set_state(state_key, f"{st.st_mtime_ns}:{offset + len(data)}")
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
