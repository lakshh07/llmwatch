import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
import redis
from conftest import FakeStreamRedis, make_event
from llmwatch_server.config import Settings
from llmwatch_server.streams import StreamConsumer
from llmwatch_server.worker import parse_messages, process_batch
from sqlalchemy import Engine


def test_worker_parse_messages() -> None:
    messages = [
        ("1", {"data": json.dumps(make_event())}),
        (
            "2",
            {
                "data": json.dumps(
                    make_event(
                        id="456",
                        model="gpt-6.2-astra",
                        input_tokens=1_000,
                        output_tokens=500,
                    )
                )
            },
        ),
        ("3", {"data": "invalid_json"}),
        ("4", {}),
        ("5", None),
    ]

    rows, ok_ids, bad = parse_messages(messages)  # type: ignore[arg-type]

    assert [row["id"] for row in rows] == ["123", "456"]
    assert [row["cost"] for row in rows] == [None, pytest.approx(0.028)]
    assert ok_ids == ["1", "2"]
    assert [msg_id for msg_id, _fields, _reason in bad] == ["3", "4", "5"]
    assert bad[0][1] == {"data": "invalid_json"}
    assert "ValidationError" in bad[0][2]


class FakeEngine:
    """Pretends Postgres inserted only the event ids in `new_ids`."""

    def __init__(self, new_ids: list[str]) -> None:
        self.new_ids = new_ids
        self.statements = 0

    @contextmanager
    def begin(self) -> Iterator["FakeEngine"]:
        yield self

    def execute(self, _statement) -> Any:
        self.statements += 1
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: self.new_ids)
        )


def run_batch(
    messages: list[tuple[str, dict[str, str]]],
    new_ids: list[str],
    judge_enabled: bool,
) -> tuple[FakeStreamRedis, FakeEngine]:
    r = FakeStreamRedis()
    engine = FakeEngine(new_ids)
    consumer = StreamConsumer(cast(redis.Redis, r), "events", "workers", "w1", "dead")
    settings = SimpleNamespace(
        judge_enabled=judge_enabled, judge_stream="judge", stream_maxlen=1000
    )
    process_batch(
        messages,
        r=cast(redis.Redis, r),
        engine=cast(Engine, engine),
        consumer=consumer,
        settings=cast(Settings, settings),
    )
    return r, engine


def test_process_batch_dead_letters_bad_messages_and_acks_the_rest() -> None:
    messages = [
        ("1", {"data": json.dumps(make_event(id="a"))}),
        ("2", {"data": "not json"}),
    ]

    r, _engine = run_batch(messages, new_ids=["a"], judge_enabled=False)

    assert r.added["dead"][0]["original_id"] == "2"
    assert sorted(r.acked) == ["1", "2"]
    assert "judge" not in r.added


def test_process_batch_queues_only_new_events_for_the_judge() -> None:
    messages = [
        ("1", {"data": json.dumps(make_event(id="new"))}),
        ("2", {"data": json.dumps(make_event(id="duplicate"))}),
    ]

    r, engine = run_batch(messages, new_ids=["new"], judge_enabled=True)

    assert r.added["judge"] == [{"event_id": "new"}]
    assert r.acked == ["1", "2"]
    assert engine.statements == 2  # events insert + rule scores insert


def test_process_batch_does_not_ack_when_the_database_fails() -> None:
    class BrokenEngine(FakeEngine):
        def execute(self, _statement) -> Any:
            raise RuntimeError("database is down")

    r = FakeStreamRedis()
    consumer = StreamConsumer(cast(redis.Redis, r), "events", "workers", "w1", "dead")

    with pytest.raises(RuntimeError):
        process_batch(
            [("1", {"data": json.dumps(make_event())})],
            r=cast(redis.Redis, r),
            engine=cast(Engine, BrokenEngine([])),
            consumer=consumer,
            settings=cast(Settings, SimpleNamespace(judge_enabled=False)),
        )

    # Not acked -> stays pending -> reclaimed later.
    assert r.acked == []
