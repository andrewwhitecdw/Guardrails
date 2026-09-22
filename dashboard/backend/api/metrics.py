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

import time

from fastapi import APIRouter, Query, Request

from ..queries import overview_stats, rails_frequency

router = APIRouter(prefix="/api/metrics")


def _range(start: int | None, end: int | None) -> tuple[int, int]:
    now = int(time.time() * 1000)
    return (start if start is not None else now - 15 * 60 * 1000), (end if end is not None else now)


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
