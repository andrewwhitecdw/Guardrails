import pytest

from backend.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        guardrails_url="http://guardrails:8000",
        db_path=str(tmp_path / "dashboard.db"),
        trace_globs=[],
        prom_url=None,
    )
