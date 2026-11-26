import socket
from typing import Any

import redis
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert

from .config import Settings, get_settings
from .db import EventRow, ScoreRow, get_engine
from .evaluators import run_rules
from .migrate import check_schema
from .models import Event
from .pricing import compute_cost
from .redis_client import get_redis
from .streams import Message, StreamConsumer

BadMessage = tuple[str, dict[str, str], str]


def parse_messages(
    messages: list[Message],
) -> tuple[list[dict[str, Any]], list[str], list[BadMessage]]:
    """Split a batch into event rows (+ their message ids) and bad messages."""
    rows: list[dict[str, Any]] = []
    ok_ids: list[str] = []
    bad: list[BadMessage] = []

    for msg_id, fields in messages:
        try:
            event = Event.model_validate_json(fields["data"])
        except (KeyError, TypeError, ValidationError) as e:
            # TypeError: fields is None for an entry trimmed from the stream.
            bad.append((msg_id, fields or {}, f"{type(e).__name__}: {e}"))
            continue
        ok_ids.append(msg_id)
        rows.append(
            {
                **event.model_dump(),
                "cost": compute_cost(
                    event.model, event.input_tokens, event.output_tokens
                ),
            }
        )

    return rows, ok_ids, bad


def process_batch(
    messages: list[Message],
    *,
    r: redis.Redis,
    engine: Engine,
    consumer: StreamConsumer,
    settings: Settings,
) -> None:
    rows, ok_ids, bad = parse_messages(messages)
    for msg_id, fields, reason in bad:
        consumer.dead_letter(msg_id, fields, reason)

    new_ids: list[str] = []
    scores: list[dict[str, Any]] = []
    if rows:
        stmt = (
            insert(EventRow)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(EventRow.id)
        )
        with engine.begin() as conn:
            # Duplicates skipped by ON CONFLICT are not returned, so only
            # brand-new events get scored (no double scores on replay).
            inserted = set(conn.execute(stmt).scalars().all())
            new_rows = [row for row in rows if row["id"] in inserted]
            new_ids = [row["id"] for row in new_rows]
            for row in new_rows:
                scores.extend(run_rules(row))
            if scores:
                conn.execute(insert(ScoreRow).values(scores))

    # The slow LLM judge runs in its own process (judge_worker.py). We only
    # hand it the ids of new events, so a slow or down API never holds up saving.
    if settings.judge_enabled and new_ids:
        pipe = r.pipeline()
        for event_id in new_ids:
            pipe.xadd(
                settings.judge_stream,
                {"event_id": event_id},
                maxlen=settings.stream_maxlen,
                approximate=True,
            )
        pipe.execute()

    # Ack last: if we crash before this, the batch is reclaimed and replayed,
    # and ON CONFLICT DO NOTHING makes the replay harmless.
    consumer.ack(ok_ids)
    print(
        f"Processed {len(messages)} messages: {len(new_ids)} new events, "
        f"{len(rows) - len(new_ids)} duplicates, {len(scores)} rule scores, "
        f"{len(bad)} dead-lettered"
    )


def run() -> None:
    settings = get_settings()
    r = get_redis()
    engine = get_engine()
    name = socket.gethostname()

    check_schema()

    consumer = StreamConsumer(
        r,
        settings.stream_name,
        settings.consumer_group,
        name,
        settings.dead_letter_stream,
        min_idle_ms=settings.reclaim_idle_ms,
        max_deliveries=settings.max_deliveries,
    )
    consumer.ensure_group()
    print(
        f"Worker {name} started, listening to stream '{settings.stream_name}' "
        f"in group '{settings.consumer_group}'"
    )

    while True:
        messages = consumer.read()
        if messages:
            process_batch(
                messages, r=r, engine=engine, consumer=consumer, settings=settings
            )


if __name__ == "__main__":
    run()
