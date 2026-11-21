import pytest
from conftest import make_event
from llmwatch_server.evaluators import fast, not_empty, run_rules, valid_json


@pytest.mark.parametrize(
    ("output", "expected"),
    [("hi", 1.0), ("   ", 0.0), (None, 0.0)],
)
def test_not_empty(output: str | None, expected: float) -> None:
    assert not_empty(make_event(output=output)) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    [('{"a": 1}', 1.0), ("{broken", 0.0), ("plain text", None)],
)
def test_valid_json(output: str, expected: float | None) -> None:
    assert valid_json(make_event(output=output)) == expected


@pytest.mark.parametrize(("latency", "expected"), [(500, 1.0), (5000, 0.0)])
def test_fast(latency: int, expected: float) -> None:
    assert fast(make_event(latency=latency)) == expected


def test_run_rules_skips_error_event() -> None:
    assert run_rules(make_event(status="error")) == []


def test_run_rules_skips_rules_without_a_value() -> None:
    scores = run_rules(make_event(output="plain text"))

    assert len(scores) == 2
    assert {score["name"] for score in scores} == {"not_empty", "fast"}
    assert all(score["event_id"] == "123" for score in scores)
    assert all(score["source"] == "heuristic" for score in scores)
    assert all(score["comment"] is None for score in scores)
