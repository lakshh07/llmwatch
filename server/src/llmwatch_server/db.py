from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import JSON, Engine, ForeignKey, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import get_settings


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[str]
    model: Mapped[str | None]
    cost: Mapped[float | None]
    input: Mapped[Any | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
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


class ScoreRow(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str]
    value: Mapped[float]
    source: Mapped[str]
    comment: Mapped[str | None]
    created_at: Mapped[float]


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url)


def create_tables() -> None:
    Base.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
