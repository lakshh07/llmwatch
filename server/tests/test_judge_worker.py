from typing import Any, cast

import pytest
import redis
from anthropic import Anthropic
from conftest import FakeStreamRedis, make_row
from llmwatch_server import judge_worker
from llmwatch_server.db import Base, ScoreRow
from llmwatch_server.streams import StreamConsumer
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([make_row(id="fresh"), make_row(id="judged")])
        session.flush()
        session.add(
            ScoreRow(
                event_id="judged",
                name="helpfulness",
                value=0.5,
                source="model",
                created_at=1.0,
            )
        )
        session.commit()
    return engine


def test_judge_batch_scores_new_events_and_skips_the_rest(
    engine: Engine, monkeypatch
) -> None:
    judged: list[str] = []

    def fake_judge(_client: Any, event: dict[str, Any]) -> dict[str, Any]:
        judged.append(event["id"])
        assert event["output"] and event["status"] == "ok"
        return {
            "event_id": event["id"],
            "name": "helpfulness",
            "value": 1.0,
            "source": "model",
            "comment": "Helpful",
            "created_at": 2.0,
        }

    monkeypatch.setattr(judge_worker, "judge_event", fake_judge)
    r = FakeStreamRedis()
    consumer = StreamConsumer(cast(redis.Redis, r), "judge", "judges", "j1", "dead")
    messages = [
        ("1", {"event_id": "fresh"}),
        ("2", {"event_id": "judged"}),  # already has a judge score
        ("3", {"event_id": "missing"}),  # not in the database
        ("4", {"something": "else"}),  # broken message
    ]

    saved = judge_worker.judge_batch(
        messages, engine=engine, client=cast(Anthropic, object()), consumer=consumer
    )

    assert saved == 1
    assert judged == ["fresh"]
    with Session(engine) as session:
        scored = session.scalars(
            select(ScoreRow.event_id).where(ScoreRow.source == "model")
        ).all()
    assert sorted(scored) == ["fresh", "judged"]
    assert sorted(r.acked) == ["1", "2", "3", "4"]
    assert r.added["dead"][0]["original_id"] == "4"


def test_judge_batch_saves_nothing_when_the_judge_gives_no_verdict(
    engine: Engine, monkeypatch
) -> None:
    monkeypatch.setattr(judge_worker, "judge_event", lambda _client, _event: None)
    r = FakeStreamRedis()
    consumer = StreamConsumer(cast(redis.Redis, r), "judge", "judges", "j1", "dead")

    saved = judge_worker.judge_batch(
        [("1", {"event_id": "fresh"})],
        engine=engine,
        client=cast(Anthropic, object()),
        consumer=consumer,
    )

    assert saved == 0
    assert r.acked == ["1"]
