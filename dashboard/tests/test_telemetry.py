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
