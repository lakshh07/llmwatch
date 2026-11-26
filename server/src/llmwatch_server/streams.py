"""Reading a Redis stream safely with a consumer group.

Two problems this solves, for every worker that reads a stream:

1. Stuck messages. XREADGROUP with ">" only hands out *new* messages. If a
   worker crashes after reading but before XACK, its messages stay in the
   group's pending list forever. `reclaim()` uses XAUTOCLAIM to take over
   messages that have been pending longer than `min_idle_ms`, whoever owned
   them, so they get processed again.

2. Bad messages. A message we can never process (broken JSON, or one that
   crashed the worker `max_deliveries` times) is copied to a dead-letter
   stream and acked, so it stops blocking the group but is not lost.
"""

import time
from collections.abc import Callable
from typing import Any

import redis

Message = tuple[str, dict[str, str]]


class StreamConsumer:
    def __init__(
        self,
        r: redis.Redis,
        stream: str,
        group: str,
        consumer: str,
        dead_letter_stream: str,
        *,
        min_idle_ms: int = 60_000,
        max_deliveries: int = 5,
        reclaim_every_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.r = r
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.dead_letter_stream = dead_letter_stream
        self.min_idle_ms = min_idle_ms
        self.max_deliveries = max_deliveries
        self.reclaim_every_seconds = reclaim_every_seconds
        self.clock = clock
        # -inf so the first read() checks for stuck messages straight away.
        self._last_reclaim = float("-inf")

    def ensure_group(self) -> None:
        try:
            self.r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def read(self, count: int = 100, block_ms: int = 3000) -> list[Message]:
        """Next batch: stuck messages first (now and then), else new ones."""
        if self.clock() - self._last_reclaim >= self.reclaim_every_seconds:
            claimed_any, messages = self.reclaim(count)
            if not claimed_any:
                # Nothing left to take over: wait a while before checking again.
                # While there is, keep reclaiming on every read until it's drained.
                self._last_reclaim = self.clock()
            if messages:
                return messages

        response: Any = self.r.xreadgroup(
            self.group, self.consumer, {self.stream: ">"}, count=count, block=block_ms
        )
        if not response:
            return []
        _stream_name, messages = response[0]
        return messages

    def reclaim(self, count: int = 100) -> tuple[bool, list[Message]]:
        """Take over messages idle for longer than min_idle_ms.

        Returns (claimed_any, messages_to_process). Messages delivered too many
        times are dead-lettered here instead of returned.
        """
        response: Any = self.r.xautoclaim(
            self.stream,
            self.group,
            self.consumer,
            min_idle_time=self.min_idle_ms,
            start_id="0-0",
            count=count,
        )
        claimed: list[Message] = response[1]
        if not claimed:
            return False, []

        print(f"Reclaimed {len(claimed)} stuck messages from '{self.stream}'")
        deliveries = self._delivery_counts([msg_id for msg_id, _ in claimed])

        to_process: list[Message] = []
        for msg_id, fields in claimed:
            times = deliveries.get(msg_id, 0)
            if times > self.max_deliveries:
                self.dead_letter(
                    msg_id, fields or {}, f"gave up after {times} deliveries"
                )
            else:
                to_process.append((msg_id, fields))
        return True, to_process

    def _delivery_counts(self, ids: list[str]) -> dict[str, int]:
        # Stream ids sort in time order, and XAUTOCLAIM returns them in order,
        # so one XPENDING call over [first, last] covers all of them.
        pending: Any = self.r.xpending_range(
            self.stream,
            self.group,
            min=ids[0],
            max=ids[-1],
            count=len(ids),
            consumername=self.consumer,
        )
        return {p["message_id"]: p["times_delivered"] for p in pending}

    def ack(self, ids: list[str]) -> None:
        if ids:
            self.r.xack(self.stream, self.group, *ids)

    def dead_letter(self, msg_id: str, fields: dict[str, str], reason: str) -> None:
        """Park a message we can't process, and ack it in the same transaction."""
        print(f"Dead-lettering message {msg_id} from '{self.stream}': {reason}")
        pipe = self.r.pipeline()  # transaction=True by default: MULTI ... EXEC
        pipe.xadd(
            self.dead_letter_stream,
            {
                **fields,
                "original_stream": self.stream,
                "original_id": msg_id,
                "reason": reason,
            },
            maxlen=100_000,
            approximate=True,
        )
        pipe.xack(self.stream, self.group, msg_id)
        pipe.execute()
