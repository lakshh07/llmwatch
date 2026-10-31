import atexit
import queue
import threading
import time

import httpx2


class LLMWatch:
    def __init__(
        self,
        api_key: str,
        host: str = "http://localhost:8000",
        batch_size: int = 50,
        flush_interval: float = 2.0,
    ) -> None:
        self.queue: queue.Queue[dict] = queue.Queue(maxsize=10_000)
        self.http = httpx2.Client(
            base_url=host, timeout=5, headers={"Authorization": f"Bearer {api_key}"}
        )
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        atexit.register(self.flush)
        threading.Thread(target=self._loop, daemon=True).start()

    def log(self, event: dict) -> None:
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            pass  # Drop the event if the queue is full, not crashing the user main app

    def _loop(self) -> None:
        while True:
            time.sleep(self.flush_interval)
            self.flush()

    def flush(self) -> None:
        while not self.queue.empty():
            batch: list[dict] = []
            while len(batch) < self.batch_size:
                try:
                    batch.append(self.queue.get_nowait())
                except queue.Empty:
                    break
            if batch:
                try:
                    self.http.post("/v1/ingest", json={"events": batch})
                except httpx2.HTTPError:
                    pass  # Drop the batch if the request fails, not crashing the user main app
