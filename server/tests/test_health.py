from fastapi.testclient import TestClient
from llmwatch_server.app import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    res = client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
