"""Runs the LLM judge on new events, separately from the main worker.

The main worker saves events and pushes `{"event_id": ...}` onto the judge
stream. This process reads that stream, loads each event from Postgres, asks
the judge and saves the score. A slow or failing LLM API only delays scores,
never the saving of events.
"""

import socket
from typing import Any

from anthropic import Anthropic
from sqlalchemy import Engine, insert, select

from .config import get_settings
from .db import EventRow, ScoreRow, get_engine
from .judge import JUDGE_SCORE_NAME, JUDGE_SOURCE, get_anthropic, judge_event
from .migrate import check_schema
from .redis_client import get_redis
from .streams import Message, StreamConsumer


def judge_batch(
    messages: list[Message],
    *,
    engine: Engine,
    client: Anthropic,
    consumer: StreamConsumer,
) -> int:
    """Judge the events in one batch. Returns how many scores were saved."""
    ids_by_event: dict[str, list[str]] = {}
    for msg_id, fields in messages:
        event_id = (fields or {}).get("event_id")
        if not event_id:
            consumer.dead_letter(msg_id, fields or {}, "missing event_id")
            continue
        ids_by_event.setdefault(event_id, []).append(msg_id)

    if not ids_by_event:
        return 0
    event_ids = list(ids_by_event)

    with engine.connect() as conn:
        events = [
            dict(row)
            for row in conn.execute(
                select(
                    EventRow.id, EventRow.status, EventRow.input, EventRow.output
                ).where(EventRow.id.in_(event_ids))
            ).mappings()
        ]
        # A message can be delivered twice (e.g. reclaimed after a crash
        # between saving the score and acking). Don't judge (or pay) twice.
        already_judged = set(
            conn.execute(
                select(ScoreRow.event_id).where(
                    ScoreRow.event_id.in_(event_ids),
                    ScoreRow.name == JUDGE_SCORE_NAME,
                    ScoreRow.source == JUDGE_SOURCE,
                )
            ).scalars()
        )

    found = {event["id"] for event in events}
    for missing in set(event_ids) - found:
        print(f"Judge: event {missing} not found, skipping")

    scores: list[dict[str, Any]] = []
    for event in events:
        if event["id"] in already_judged:
            continue
        score = judge_event(client, event)
        if score is not None:
            scores.append(score)

    if scores:
        with engine.begin() as conn:
            conn.execute(insert(ScoreRow).values(scores))

    consumer.ack([msg_id for ids in ids_by_event.values() for msg_id in ids])
    return len(scores)


def run() -> None:
    settings = get_settings()
    r = get_redis()
    engine = get_engine()
    name = socket.gethostname()

    check_schema()
    if not settings.judge_enabled:
        print(
            "Warning: LLMWATCH_JUDGE_ENABLED is false, so the worker won't queue "
            "any events for judging. This process will sit idle."
        )

    consumer = StreamConsumer(
        r,
        settings.judge_stream,
        settings.judge_group,
        name,
        settings.dead_letter_stream,
        # Judging a batch makes many LLM calls, so give it longer before
        # another judge worker decides it is stuck and takes it over.
        min_idle_ms=max(settings.reclaim_idle_ms, 300_000),
        max_deliveries=settings.max_deliveries,
    )
    consumer.ensure_group()
    client = get_anthropic()
    print(
        f"Judge worker {name} started, listening to stream "
        f"'{settings.judge_stream}' in group '{settings.judge_group}'"
    )

    while True:
        messages = consumer.read(count=20)
        if messages:
            saved = judge_batch(
                messages, engine=engine, client=client, consumer=consumer
            )
            print(f"Judged {len(messages)} events, saved {saved} scores")


if __name__ == "__main__":
    run()
