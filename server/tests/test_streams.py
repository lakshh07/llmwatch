from typing import cast

import pytest
import redis
from conftest import FakeStreamRedis
from llmwatch_server.streams import StreamConsumer


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_consumer(
    r: FakeStreamRedis, clock: Clock | None = None, max_deliveries: int = 5
) -> StreamConsumer:
    return StreamConsumer(
        cast(redis.Redis, r),
        "events",
        "workers",
        "w1",
        "dead",
        min_idle_ms=60_000,
        max_deliveries=max_deliveries,
        reclaim_every_seconds=30,
        clock=clock or Clock(),
    )


def test_read_returns_stuck_messages_before_new_ones() -> None:
    r = FakeStreamRedis()
    r.to_claim = [("1-0", {"data": "old"})]
    r.to_read = [[("2-0", {"data": "new"})]]
    consumer = make_consumer(r)

    assert consumer.read() == [("1-0", {"data": "old"})]
    # Something was claimed, so it checks again before reading new messages.
    assert consumer.read() == [("2-0", {"data": "new"})]
    assert r.calls == ["xautoclaim", "xautoclaim", "xreadgroup"]


def test_reclaim_waits_between_checks_once_nothing_is_stuck() -> None:
    r = FakeStreamRedis()
    clock = Clock()
    consumer = make_consumer(r, clock)

    consumer.read()
    consumer.read()
    clock.now += 31
    consumer.read()

    assert r.calls == [
        "xautoclaim",
        "xreadgroup",
        "xreadgroup",
        "xautoclaim",
        "xreadgroup",
    ]


def test_reclaim_dead_letters_messages_delivered_too_often() -> None:
    r = FakeStreamRedis()
    r.to_claim = [("1-0", {"data": "poison"}), ("2-0", {"data": "retry me"})]
    r.deliveries = {"1-0": 6, "2-0": 2}
    consumer = make_consumer(r, max_deliveries=5)

    claimed_any, messages = consumer.reclaim()

    assert claimed_any
    assert messages == [("2-0", {"data": "retry me"})]
    assert r.acked == ["1-0"]
    [dead] = r.added["dead"]
    assert dead["data"] == "poison"
    assert dead["original_id"] == "1-0"
    assert dead["original_stream"] == "events"
    assert "6 deliveries" in dead["reason"]


def test_reclaim_dead_letters_trimmed_entries_with_no_fields() -> None:
    # Before Redis 7, XAUTOCLAIM returns (id, None) for entries trimmed away.
    r = FakeStreamRedis()
    r.to_claim = [("1-0", None)]  # type: ignore[list-item]
    r.deliveries = {"1-0": 9}
    consumer = make_consumer(r)

    _claimed_any, messages = consumer.reclaim()

    assert messages == []
    assert r.acked == ["1-0"]


def test_ensure_group_ignores_existing_group() -> None:
    class RedisWithGroup(FakeStreamRedis):
        def xgroup_create(self, *_args, **_kwargs) -> None:
            raise redis.ResponseError("BUSYGROUP Consumer Group name already exists")

    make_consumer(RedisWithGroup()).ensure_group()


def test_ensure_group_raises_other_errors() -> None:
    class BrokenRedis(FakeStreamRedis):
        def xgroup_create(self, *_args, **_kwargs) -> None:
            raise redis.ResponseError("WRONGTYPE")

    with pytest.raises(redis.ResponseError):
        make_consumer(BrokenRedis()).ensure_group()
