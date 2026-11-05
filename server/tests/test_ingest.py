from fastapi.testclient import TestClient
from llmwatch_server.app import create_app


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


def test_ingest_accepts_events() -> None:
    client = TestClient(create_app())

    res = client.post(
        "/v1/ingest",
        json={"events": [make_event()]},
    )

    assert res.status_code == 202
    assert res.json() == {"accepted": 1}


def test_ingest_rejects_event_missing_required_field() -> None:
    client = TestClient(create_app())

    event = make_event()
    del event["id"]

    res = client.post(
        "/v1/ingest",
        json={"events": [event]},
    )

    assert res.status_code == 422


def test_ingest_rejects_unknown_status() -> None:
    client = TestClient(create_app())

    res = client.post(
        "/v1/ingest",
        json={"events": [make_event(status="unknown")]},
    )

    assert res.status_code == 422
