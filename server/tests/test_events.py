from conftest import make_row
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-key"}


def test_events_returns_newest_first(client: TestClient, db_session) -> None:
    db_session.add_all(
        [
            make_row(id="older", start_time=1690000000.0),
            make_row(id="newer", start_time=1690000002.0),
        ]
    )
    db_session.commit()

    res = client.get("/v1/events", headers=AUTH)

    assert res.status_code == 200
    assert [event["id"] for event in res.json()] == ["newer", "older"]


def test_events_respects_limit(client: TestClient, db_session) -> None:
    db_session.add_all(
        [
            make_row(id="first", start_time=1690000000.0),
            make_row(id="second", start_time=1690000001.0),
            make_row(id="third", start_time=1690000002.0),
        ]
    )
    db_session.commit()

    res = client.get("/v1/events?limit=2", headers=AUTH)

    assert res.status_code == 200
    assert [event["id"] for event in res.json()] == ["third", "second"]


def test_events_filters_by_model(client: TestClient, db_session) -> None:
    db_session.add_all(
        [
            make_row(id="gpt", model="gpt-4"),
            make_row(id="claude", model="claude-sonnet"),
        ]
    )
    db_session.commit()

    res = client.get("/v1/events?model=gpt-4", headers=AUTH)

    assert res.status_code == 200
    assert [event["id"] for event in res.json()] == ["gpt"]


def test_events_requires_auth(client: TestClient) -> None:
    res = client.get("/v1/events")

    assert res.status_code == 401


def test_events_rejects_zero_limit(client: TestClient) -> None:
    res = client.get("/v1/events?limit=0", headers=AUTH)

    assert res.status_code == 422
