from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Event(BaseModel):
    id: str
    type: Literal["generation"]
    model: str | None = None
    input: Any = None
    output: str | None = None
    start_time: float
    end_time: float
    latency: float
    ttft: float | None = Field(None, description="Time to first token in milliseconds")
    status: Literal["incomplete", "ok", "error"]
    error: str | None = None
    parse_error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class IngestRequest(BaseModel):
    events: list[Event]


class EventOut(Event):
    cost: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ModelStats(BaseModel):
    model: str | None
    events: int
    cost: float


class ScoreStats(BaseModel):
    name: str
    source: str
    count: int
    avg: float


class StatsOut(BaseModel):
    total_events: int
    total_cost: float
    avg_latency: float
    error_count: int
    by_model: list[ModelStats]
    scores: list[ScoreStats]


class ScoreIn(BaseModel):
    name: str
    value: float = Field(ge=0, le=1)
    source: Literal["human", "model", "heuristic"]
    comment: str | None = None


class ScoreOut(ScoreIn):
    id: int
    event_id: str
    created_at: float

    model_config = ConfigDict(from_attributes=True)


class AlertRuleIn(BaseModel):
    name: str
    metric: Literal["error_rate", "avg_latency", "total_cost", "avg_score"]
    op: Literal["above", "below"]
    threshold: float
    window_minutes: int = Field(60, ge=1, le=1440)
    score_name: str | None = None
    webhook_url: str | None = None

    @model_validator(mode="after")
    def check_score_name(self) -> "AlertRuleIn":
        # avg_score needs to know which score to average (e.g. "helpfulness").
        if self.metric == "avg_score" and not self.score_name:
            raise ValueError("score_name is required when metric is 'avg_score'")
        return self


class AlertRuleOut(AlertRuleIn):
    id: int
    enabled: bool
    created_at: float
    firing: bool
    last_value: float | None
    last_checked_at: float | None
    last_fired_at: float | None

    model_config = ConfigDict(from_attributes=True)
