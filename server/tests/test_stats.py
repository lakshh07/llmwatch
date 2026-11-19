import pytest
from conftest import make_row
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-key"}


def test_stats_returns_zeroes_for_empty_database(client: TestClient) -> None:
    response = client.get("/v1/stats", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {
        "total_events": 0,
        "total_cost": 0,
        "avg_latency": 0,
        "error_count": 0,
        "by_model": [],
    }


def test_stats_aggregates_events_and_costs(client: TestClient, db_session) -> None:
    db_session.add_all(
        [
            make_row(id="one", model="gpt-4", cost=0.10, latency=100),
            make_row(id="two", model="gpt-4", cost=0.20, latency=200),
            make_row(
                id="three",
                model="claude-sonnet",
                cost=0.50,
                latency=300,
                status="error",
            ),
        ]
    )
    db_session.commit()

    response = client.get("/v1/stats", headers=AUTH)

    assert response.status_code == 200
    stats = response.json()
    assert stats["total_events"] == 3
    assert stats["total_cost"] == pytest.approx(0.80)
    assert stats["avg_latency"] == pytest.approx(200)
    assert stats["error_count"] == 1
    assert stats["by_model"] == [
        {"model": "claude-sonnet", "events": 1, "cost": pytest.approx(0.50)},
        {"model": "gpt-4", "events": 2, "cost": pytest.approx(0.30)},
    ]


def test_stats_requires_auth(client: TestClient) -> None:
    response = client.get("/v1/stats")

    assert response.status_code == 401
