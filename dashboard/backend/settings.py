from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NGDASH_")

    guardrails_url: str = "http://127.0.0.1:8000"
    host: str = "127.0.0.1"
    port: int = 8500
    db_path: str = "~/.nemoguardrails/dashboard/dashboard.db"
    trace_globs: list[str] = []
    prom_url: str | None = None
    scrape_interval: float = 15.0
    usage_stats_path: str = "~/.config/nemoguardrails/usage_stats.json"
    static_dir: str = "frontend/dist"
