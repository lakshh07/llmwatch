from typing import Any, Literal

from pydantic import BaseModel, Field


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
