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
        n = len(durations)
        rank = p / 100 * n
        if rank == int(rank) and 0 < rank < n:
            idx = int(rank)
            return (durations[idx - 1] + durations[idx]) / 2 * 1000
        idx = max(0, min(n - 1, math.ceil(rank) - 1))
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
    ranked = sorted(
        counts.items(),
        key=lambda kv: (kv[1], blocked_counts.get(kv[0], 0)),
        reverse=True,
    )
    return [
        {"name": name, "count": count, "blocked": blocked_counts.get(name, 0)}
        for name, count in ranked[:limit]
    ]
