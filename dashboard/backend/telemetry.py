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
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return events[-limit:]
