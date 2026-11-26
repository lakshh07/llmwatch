from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLMWATCH_", env_file=".env")

    database_url: str
    redis_url: str = "redis://localhost:6379"
    stream_name: str = "llmwatch:events"
    stream_maxlen: int = 1_000_000
    consumer_group: str = "llmwatch-workers"
    dead_letter_stream: str = "llmwatch:dead-letter"
    # A message pending this long is treated as stuck (its worker died) and
    # taken over by another worker. Keep it well above a normal batch time.
    reclaim_idle_ms: int = 60_000
    max_deliveries: int = 5
    judge_stream: str = "llmwatch:judge"
    judge_group: str = "llmwatch-judges"
    api_key: str
    judge_enabled: bool = False
    judge_model: str = "claude-haiku-5-5"
    anthropic_api_key: str | None = None
    alert_interval_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # Fields are read from env, not passed in
