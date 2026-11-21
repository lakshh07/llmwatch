from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest
from anthropic import Anthropic
from conftest import make_event
from httpx2 import Request
from llmwatch_server import judge
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch) -> None:
    # Keep these tests independent of .env / real environment variables.
    monkeypatch.setattr(
        judge, "get_settings", lambda: SimpleNamespace(judge_model="test-model")
    )


class FakeMessages:
    def __init__(
        self, response: SimpleNamespace, error: Exception | None = None
    ) -> None:
        self.response = response
        self.error = error
        self.parse_calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.parse_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeAnthropic:
    def __init__(
        self, response: SimpleNamespace, error: Exception | None = None
    ) -> None:
        self.messages = FakeMessages(response, error)


def make_client(
    score: int = 5,
    reason: str = "Directly answers the question.",
    stop_reason: str = "end_turn",
    error: Exception | None = None,
) -> FakeAnthropic:
    response = SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=judge.JudgeVerdict(score=score, reason=reason),
    )
    return FakeAnthropic(response, error)


@pytest.mark.parametrize(("score_value", "expected"), [(5, 1.0), (1, 0.0)])
def test_judge_event_maps_verdict_score(score_value: int, expected: float) -> None:
    client = make_client(score=score_value)

    score = judge.judge_event(cast(Anthropic, client), make_event())

    assert score is not None
    assert score["name"] == "helpfulness"
    assert score["value"] == expected
    assert score["source"] == "model"
    assert score["comment"] == "Directly answers the question."
    assert client.messages.parse_calls[0]["model"] == "test-model"
    assert client.messages.parse_calls[0]["output_format"] is judge.JudgeVerdict


def test_judge_event_skips_error_event() -> None:
    client = make_client()

    assert (
        judge.judge_event(cast(Anthropic, client), make_event(status="error")) is None
    )
    assert judge.judge_event(cast(Anthropic, client), make_event(output="  ")) is None
    assert client.messages.parse_calls == []


def test_judge_event_skips_refusal() -> None:
    client = make_client(stop_reason="refusal")

    assert judge.judge_event(cast(Anthropic, client), make_event()) is None


def test_judge_event_handles_anthropic_api_error(capsys) -> None:
    error = anthropic.APIError(
        "request failed",
        request=Request("POST", "https://api.anthropic.com"),
        body=None,
    )
    client = make_client(error=error)

    assert judge.judge_event(cast(Anthropic, client), make_event()) is None
    assert "request failed" in capsys.readouterr().out


def test_judge_event_handles_out_of_range_score(capsys) -> None:
    with pytest.raises(ValidationError) as exc_info:
        judge.JudgeVerdict.model_validate({"score": 6, "reason": "too high"})
    client = make_client(error=exc_info.value)

    assert judge.judge_event(cast(Anthropic, client), make_event()) is None
    assert "Judge failed" in capsys.readouterr().out


def test_judge_event_skips_missing_verdict(capsys) -> None:
    client = make_client(stop_reason="max_tokens")
    client.messages.response.parsed_output = None

    assert judge.judge_event(cast(Anthropic, client), make_event()) is None
    assert "max_tokens" in capsys.readouterr().out
