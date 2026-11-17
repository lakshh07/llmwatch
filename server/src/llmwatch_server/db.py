from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import get_settings


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str]
    model: Mapped[str | None]
    cost: Mapped[float | None]
    input: Mapped[Any | None] = mapped_column(JSONB)
    output: Mapped[str | None]
    start_time: Mapped[float]
    end_time: Mapped[float]
    latency: Mapped[float]
    ttft: Mapped[float | None]
    status: Mapped[str]
    error: Mapped[str | None]
    parse_error: Mapped[str | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url)


def create_tables() -> None:
    Base.metadata.create_all(get_engine())
