import pytest
import redis
from fastapi.testclient import TestClient
from llmwatch_server.app import create_app
from llmwatch_server.config import Settings, get_settings
from llmwatch_server.db import Base, EventRow, get_session
from llmwatch_server.redis_client import get_redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


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
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(fake_redis: FakeRedis, db_session) -> TestClient:
    app = create_app()
    app.dependency_overrides = {
        get_settings: lambda: Settings(
            api_key="test-key", database_url="sqlite:///test.db"
        ),
        get_redis: lambda: fake_redis,
        get_session: lambda: db_session,
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


def make_row(**overrides) -> EventRow:
    return EventRow(**make_event(**overrides))
