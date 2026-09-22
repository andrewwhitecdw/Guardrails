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
