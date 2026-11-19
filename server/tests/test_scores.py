from conftest import make_row
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-key"}


def test_create_then_list_score(client: TestClient, db_session) -> None:
    db_session.add(make_row(id="event-1"))
    db_session.commit()

    created = client.post(
        "/v1/events/event-1/scores",
        headers=AUTH,
        json={
            "name": "accuracy",
            "value": 0.9,
            "source": "human",
            "comment": "Looks correct",
        },
    )

    assert created.status_code == 201
    score = created.json()
    assert score["id"] > 0
    assert score["event_id"] == "event-1"
    assert score["name"] == "accuracy"
    assert score["value"] == 0.9
    assert score["source"] == "human"
    assert score["comment"] == "Looks correct"
    assert isinstance(score["created_at"], float)

    listed = client.get("/v1/events/event-1/scores", headers=AUTH)

    assert listed.status_code == 200
    assert listed.json() == [score]


def test_create_score_rejects_unknown_event(client: TestClient) -> None:
    res = client.post(
        "/v1/events/unknown/scores",
        headers=AUTH,
        json={"name": "accuracy", "value": 0.5, "source": "heuristic"},
    )

    assert res.status_code == 404


def test_create_score_rejects_value_above_one(client: TestClient) -> None:
    res = client.post(
        "/v1/events/unknown/scores",
        headers=AUTH,
        json={"name": "accuracy", "value": 1.5, "source": "human"},
    )

    assert res.status_code == 422


def test_create_score_rejects_bad_source(client: TestClient) -> None:
    res = client.post(
        "/v1/events/unknown/scores",
        headers=AUTH,
        json={"name": "accuracy", "value": 0.5, "source": "unknown"},
    )

    assert res.status_code == 422


def test_scores_require_auth(client: TestClient) -> None:
    post_res = client.post(
        "/v1/events/event-1/scores",
        json={"name": "accuracy", "value": 0.5, "source": "model"},
    )
    get_res = client.get("/v1/events/event-1/scores")

    assert post_res.status_code == 401
    assert get_res.status_code == 401
