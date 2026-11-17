import socket
from typing import Any

import redis
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert

from .config import get_settings
from .db import EventRow, create_tables, get_engine
from .models import Event
from .redis_client import get_redis

Message = tuple[str, dict[str, str]]


def ensure_group(r: redis.Redis, stream: str, group: str) -> None:
    try:
        r.xgroup_create(stream, group, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def parse_messages(
    messages: list[Message],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    ids: list[str] = []

    for msg_id, fields in messages:
        ids.append(msg_id)
        try:
            event = Event.model_validate_json(fields["data"])
        except (KeyError, ValidationError) as e:
            print(f"Failed to parse message (bad message) {msg_id}: {e}")
            continue
        rows.append(event.model_dump())

    return rows, ids


def run() -> None:
    settings = get_settings()
    r = get_redis()
    engine = get_engine()
    stream = settings.stream_name
    group = settings.consumer_group
    consumer = socket.gethostname()

    # Create the database tables if they don't exist
    create_tables()

    ensure_group(r, stream, group)
    print(
        f"Worker {consumer} started, listening to stream '{stream}' in group '{group}'"
    )

    while True:
        response: Any = r.xreadgroup(
            group, consumer, {stream: ">"}, count=100, block=3000
        )
        if not response:
            continue

        _stream_name, messages = response[0]
        rows, ids = parse_messages(messages)

        if rows:
            stmt = (
                insert(EventRow)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            with engine.begin() as conn:
                conn.execute(stmt)

        r.xack(stream, group, *ids)
        print(
            f"Worker {consumer} processed {len(rows)} events and acknowledged {len(ids)} messages"
        )


if __name__ == "__main__":
    run()
