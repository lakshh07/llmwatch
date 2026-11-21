from typing import Any

from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-key"}


def make_rule(**overrides: Any) -> dict[str, Any]:
    rule = {
        "name": "Too many errors",
        "metric": "error_rate",
        "op": "above",
        "threshold": 0.1,
    }
    rule.update(overrides)
    return rule


def test_create_and_list_alert_rules(client: TestClient) -> None:
    response = client.post("/v1/alerts", json=make_rule(), headers=AUTH)

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Too many errors"
    assert created["window_minutes"] == 60
    assert created["enabled"] is True
    assert created["firing"] is False
    assert created["last_value"] is None

    listed = client.get("/v1/alerts", headers=AUTH).json()
    assert [rule["id"] for rule in listed] == [created["id"]]


def test_create_alert_rejects_unknown_metric(client: TestClient) -> None:
    response = client.post("/v1/alerts", json=make_rule(metric="vibes"), headers=AUTH)

    assert response.status_code == 422


def test_avg_score_alert_requires_score_name(client: TestClient) -> None:
    rule = make_rule(metric="avg_score", op="below", threshold=0.5)

    assert client.post("/v1/alerts", json=rule, headers=AUTH).status_code == 422
    rule["score_name"] = "helpfulness"
    assert client.post("/v1/alerts", json=rule, headers=AUTH).status_code == 201


def test_delete_alert_rule(client: TestClient) -> None:
    rule_id = client.post("/v1/alerts", json=make_rule(), headers=AUTH).json()["id"]

    assert client.delete(f"/v1/alerts/{rule_id}", headers=AUTH).status_code == 204
    assert client.delete(f"/v1/alerts/{rule_id}", headers=AUTH).status_code == 404
    assert client.get("/v1/alerts", headers=AUTH).json() == []


def test_alerts_require_auth(client: TestClient) -> None:
    assert client.get("/v1/alerts").status_code == 401
