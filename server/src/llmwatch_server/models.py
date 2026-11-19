from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class StatsOut(BaseModel):
    total_events: int
    total_cost: float
    avg_latency: float
    error_count: int
    by_model: list[ModelStats]
