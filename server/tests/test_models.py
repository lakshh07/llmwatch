from typing import Literal

import pytest
from llmwatch_server.models import ScoreIn, ScoreOut
from pydantic import ValidationError


@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_score_rejects_values_outside_range(value: float) -> None:
    with pytest.raises(ValidationError):
        ScoreIn(name="accuracy", value=value, source="human")


@pytest.mark.parametrize("source", ["human", "model", "heuristic"])
def test_score_accepts_supported_sources(
    source: Literal["human", "model", "heuristic"],
) -> None:
    score = ScoreIn(name="accuracy", value=0.5, source=source)
    assert score.source == source


def test_score_out_from_attributes() -> None:
    class ScoreAttributes:
        id = 1
        event_id = "event-1"
        created_at = 1690000000.0
        name = "accuracy"
        value = 0.9
        source = "model"
        comment = None

    score = ScoreOut.model_validate(ScoreAttributes())

    assert score.id == 1
    assert score.event_id == "event-1"
