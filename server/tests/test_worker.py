import json
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from conftest import make_event
from llmwatch_server import worker
from llmwatch_server.worker import parse_messages


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
    ]

    rows, ids = parse_messages(messages)

    assert len(rows) == 2
    assert len(ids) == 4
    assert [row["id"] for row in rows] == ["123", "456"]
    assert [row["cost"] for row in rows] == [None, pytest.approx(0.028)]
    assert ids == ["1", "2", "3", "4"]


def test_worker_judges_new_events_after_event_transaction(monkeypatch, capsys) -> None:
    class FakeResult:
        def scalars(self) -> "FakeResult":
            return self

        def all(self) -> list[str]:
            return ["123"]

    class FakeEngine:
        def __init__(self) -> None:
            self.in_transaction = False
            self.statement_counts: list[int] = []

        @contextmanager
        def begin(self) -> Iterator["FakeConnection"]:
            self.in_transaction = True
            self.statement_counts.append(0)
            try:
                yield FakeConnection(self)
            finally:
                self.in_transaction = False

    class FakeConnection:
        def __init__(self, engine: FakeEngine) -> None:
            self.engine = engine

        def execute(self, _statement) -> FakeResult:
            self.engine.statement_counts[-1] += 1
            return FakeResult()

    class FakeRedis:
        def __init__(self) -> None:
            self.read_count = 0

        def xgroup_create(self, *_args, **_kwargs) -> None:
            pass

        def xreadgroup(self, *_args, **_kwargs):
            self.read_count += 1
            if self.read_count > 1:
                raise StopIteration
            messages = [
                ("1", {"data": json.dumps(make_event())}),
                ("2", {"data": json.dumps(make_event(id="456"))}),
            ]
            return [("stream", messages)]

        def xack(self, *_args) -> None:
            pass

    engine = FakeEngine()
    redis_client = FakeRedis()
    judged_ids: list[str] = []

    def fake_judge(_client, event):
        assert not engine.in_transaction
        judged_ids.append(event["id"])
        return {
            "event_id": event["id"],
            "name": "helpfulness",
            "value": 1.0,
            "source": "model",
            "comment": "Helpful",
            "created_at": 1.0,
        }

    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            stream_name="stream", consumer_group="workers", judge_enabled=True
        ),
    )
    monkeypatch.setattr(worker, "get_redis", lambda: redis_client)
    monkeypatch.setattr(worker, "get_engine", lambda: engine)
    monkeypatch.setattr(worker, "check_schema", lambda: None)
    monkeypatch.setattr(worker, "get_anthropic", object)
    monkeypatch.setattr(worker, "judge_event", fake_judge)

    with pytest.raises(StopIteration):
        worker.run()

    assert judged_ids == ["123"]
    assert engine.statement_counts == [2, 1]
    assert "1 judge scores" in capsys.readouterr().out
