import socket
from typing import Any

import redis
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert

from .config import get_settings
from .db import EventRow, ScoreRow, get_engine
from .evaluators import run_rules
from .judge import get_anthropic, judge_event
from .migrate import check_schema
from .models import Event
from .pricing import compute_cost
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
        rows.append(
            {
                **event.model_dump(),
                "cost": compute_cost(
                    event.model, event.input_tokens, event.output_tokens
                ),
            }
        )

    return rows, ids


def run() -> None:
    settings = get_settings()
    r = get_redis()
    engine = get_engine()
    stream = settings.stream_name
    group = settings.consumer_group
    consumer = socket.gethostname()

    check_schema()

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

        scores: list[dict[str, Any]] = []
        judge_scores: list[dict[str, Any]] = []
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
                for row in new_rows:
                    scores.extend(run_rules(row))
                if scores:
                    conn.execute(insert(ScoreRow).values(scores))

            if settings.judge_enabled and new_rows:
                client = get_anthropic()
                for row in new_rows:
                    score = judge_event(client, row)
                    if score is not None:
                        judge_scores.append(score)
                if judge_scores:
                    with engine.begin() as conn:
                        conn.execute(insert(ScoreRow).values(judge_scores))

        r.xack(stream, group, *ids)
        print(
            f"Worker {consumer} processed {len(rows)} events, saved {len(scores)} "
            f"scores and {len(judge_scores)} judge scores and acknowledged "
            f"{len(ids)} messages"
        )


if __name__ == "__main__":
    run()
