from conftest import FakeRedis, FakeRedisWithError
from fastapi.testclient import TestClient
from llmwatch_server.models import Event

AUTH = {"Authorization": "Bearer test-key"}


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


def test_ingest_accepts_events(client: TestClient, fake_redis: FakeRedis) -> None:
    res = client.post(
        "/v1/ingest",
        headers=AUTH,
        json={"events": [make_event(), make_event(id="456")]},
    )

    assert res.status_code == 202
    assert res.json() == {"accepted": 2}

    entries = fake_redis.streams["llmwatch:events"]

    assert len(entries) == 2
    assert Event.model_validate_json(entries[0]["data"]).id == "123"
    assert Event.model_validate_json(entries[1]["data"]).id == "456"


def test_ingest_rejects_event_missing_required_field(client: TestClient) -> None:
    event = make_event()
    del event["id"]

    res = client.post(
        "/v1/ingest",
        headers=AUTH,
        json={"events": [event]},
    )

    assert res.status_code == 422


def test_ingest_rejects_unknown_status(client: TestClient) -> None:
    res = client.post(
        "/v1/ingest",
        headers=AUTH,
        json={"events": [make_event(status="unknown")]},
    )

    assert res.status_code == 422


def test_ingest_rejects_invalid_api_key(client: TestClient) -> None:
    res = client.post(
        "/v1/ingest",
        headers={"Authorization": "Bearer invalid-key"},
        json={"events": [make_event()]},
    )

    assert res.status_code == 401


def test_ingest_rejects_missing_api_key(client: TestClient) -> None:
    res = client.post(
        "/v1/ingest",
        json={"events": [make_event()]},
    )

    assert res.status_code == 401


def test_ingest_rejects_invalid_api_key_format(client: TestClient) -> None:
    res = client.post(
        "/v1/ingest",
        headers={"Authorization": "InvalidFormat test-key"},
        json={"events": [make_event()]},
    )

    assert res.status_code == 401


def test_ingest_handles_redis_connection_error(client: TestClient) -> None:
    from llmwatch_server.redis_client import get_redis

    client.app.dependency_overrides[get_redis] = lambda: FakeRedisWithError()  # type: ignore

    res = client.post(
        "/v1/ingest",
        headers=AUTH,
        json={"events": [make_event()]},
    )

    assert res.status_code == 503
