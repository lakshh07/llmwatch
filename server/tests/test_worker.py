import json

from conftest import make_event
from llmwatch_server.worker import parse_messages


def test_worker_parse_messages() -> None:
    messages = [
        ("1", {"data": json.dumps(make_event())}),
        ("2", {"data": json.dumps(make_event(id="456"))}),
        ("3", {"data": "invalid_json"}),
        ("4", {}),
    ]

    rows, ids = parse_messages(messages)

    assert len(rows) == 2
    assert len(ids) == 4
    assert [row["id"] for row in rows] == ["123", "456"]
    assert ids == ["1", "2", "3", "4"]
