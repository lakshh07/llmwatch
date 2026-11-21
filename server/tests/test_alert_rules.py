from typing import Any

import pytest
from conftest import make_row
from llmwatch_server.alerts import check_rules, compute_metric, is_breached
from llmwatch_server.db import AlertRuleRow, ScoreRow

NOW = 1_700_000_000.0
RECENT = NOW - 60  # 1 minute ago: inside a 60-minute window
OLD = NOW - 2 * 60 * 60  # 2 hours ago: outside it


def make_alert(**overrides: Any) -> AlertRuleRow:
    fields: dict[str, Any] = {
        "name": "Too many errors",
        "metric": "error_rate",
        "op": "above",
        "threshold": 0.1,
        "window_minutes": 60,
        "webhook_url": "https://hooks.example.com/x",
        "created_at": NOW,
    }
    fields.update(overrides)
    return AlertRuleRow(**fields)


class FakeSender:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, payload: dict[str, Any]) -> None:
        self.calls.append((url, payload))


@pytest.fixture
def events(db_session) -> None:
    db_session.add_all(
        [
            make_row(id="a", start_time=RECENT, latency=100, cost=0.25),
            make_row(id="b", start_time=RECENT, latency=300, cost=0.25, status="error"),
            make_row(id="old", start_time=OLD, latency=9999, cost=5, status="error"),
        ]
    )
    db_session.add_all(
        [
            ScoreRow(
                event_id="a",
                name="helpfulness",
                value=1.0,
                source="model",
                created_at=RECENT,
            ),
            ScoreRow(
                event_id="b",
                name="helpfulness",
                value=0.0,
                source="model",
                created_at=RECENT,
            ),
            ScoreRow(
                event_id="old",
                name="helpfulness",
                value=0.0,
                source="model",
                created_at=OLD,
            ),
        ]
    )
    db_session.commit()


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        ("error_rate", 0.5),
        ("avg_latency", 200),
        ("total_cost", 0.5),
        ("avg_score", 0.5),
    ],
)
def test_compute_metric_only_counts_the_window(
    db_session, events, metric: str, expected: float
) -> None:
    rule = make_alert(metric=metric, score_name="helpfulness")

    assert compute_metric(db_session, rule, NOW) == pytest.approx(expected)


def test_compute_metric_with_no_data(db_session) -> None:
    assert compute_metric(db_session, make_alert(metric="error_rate"), NOW) is None
    assert compute_metric(db_session, make_alert(metric="total_cost"), NOW) == 0.0


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("above", 0.2, True),
        ("above", 0.1, False),  # equal to the threshold is not a breach
        ("below", 0.05, True),
        ("below", 0.2, False),
        ("above", None, False),  # no data never fires
    ],
)
def test_is_breached(op: str, value: float | None, expected: bool) -> None:
    assert is_breached(make_alert(op=op, threshold=0.1), value) is expected


def test_check_rules_notifies_only_on_state_change(db_session, events) -> None:
    rule = make_alert()  # error rate is 0.5, threshold 0.1 -> breached
    db_session.add(rule)
    db_session.commit()
    send = FakeSender()

    # 1st check: ok -> firing, one notification.
    assert check_rules(db_session, NOW, send) == 1
    assert rule.firing is True
    assert rule.last_value == pytest.approx(0.5)
    assert rule.last_fired_at == NOW
    assert send.calls[0][0] == "https://hooks.example.com/x"
    assert "Too many errors" in send.calls[0][1]["text"]

    # 2nd check: still firing, no new notification.
    assert check_rules(db_session, NOW + 60, send) == 0
    assert rule.last_checked_at == NOW + 60

    # Raise the threshold: firing -> resolved, one more notification.
    rule.threshold = 0.9
    assert check_rules(db_session, NOW + 120, send) == 1
    assert rule.firing is False
    assert "resolved" in send.calls[1][1]["text"]


def test_check_rules_skips_disabled_rules(db_session, events) -> None:
    rule = make_alert(enabled=False)
    db_session.add(rule)
    db_session.commit()

    assert check_rules(db_session, NOW, FakeSender()) == 0
    assert rule.firing is False
    assert rule.last_checked_at is None


def test_check_rules_resolves_when_window_has_no_data(db_session, events) -> None:
    rule = make_alert()
    db_session.add(rule)
    db_session.commit()
    send = FakeSender()
    check_rules(db_session, NOW, send)

    # A day later the window is empty: no data -> not breached -> resolved.
    assert check_rules(db_session, NOW + 24 * 60 * 60, send) == 1
    assert rule.firing is False
    assert rule.last_value is None
    assert "no error_rate data" in send.calls[1][1]["text"]
