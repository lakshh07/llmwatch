from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLMWATCH_", env_file=".env")

    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    stream_name: str = "llmwatch:events"
    stream_maxlen: int = 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # Fields are read from env, not passed in
