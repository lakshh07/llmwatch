import pytest
import redis
from fastapi.testclient import TestClient
from llmwatch_server.app import create_app
from llmwatch_server.config import Settings, get_settings
from llmwatch_server.redis_client import get_redis


class FakeRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[dict[str, str]]] = {}

    def pipeline(self) -> "FakeRedis":
        return self

    def xadd(
        self, name: str, fields: dict[str, str], maxlen: int | None = None
    ) -> None:
        self.streams.setdefault(name, []).append(fields)

    def execute(self) -> list[None]:
        return []


class FakeRedisWithError(FakeRedis):
    def execute(self) -> list[None]:
        raise redis.ConnectionError("Simulated Redis connection error")


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def client(fake_redis: FakeRedis) -> TestClient:
    app = create_app()
    app.dependency_overrides = {
        get_settings: lambda: Settings(
            api_key="test-key", database_url="sqlite:///test.db"
        ),
        get_redis: lambda: fake_redis,
    }

    return TestClient(app)


def make_event(**overrides):
    event = {
        "id": "123",
        "type": "generation",
        "model": "gpt-4",
        "input": [{"role": "user", "content": "Hello"}],
        "output": "Hello! How can I assist you today?",
        "status": "ok",
        "start_time": 1690000000.0,
        "end_time": 1690000001.0,
        "latency": 1000,
    }
    event.update(overrides)
    return event
