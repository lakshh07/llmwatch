from fastapi.testclient import TestClient

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


def test_ingest_accepts_events(client: TestClient) -> None:
    res = client.post(
        "/v1/ingest",
        headers=AUTH,
        json={"events": [make_event()]},
    )

    assert res.status_code == 202
    assert res.json() == {"accepted": 1}


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
