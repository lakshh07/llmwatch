import json
import time
from functools import partial

import httpx
import pytest
from llmwatch import LLMWatch
from llmwatch import client as client_module


class FakeServer:
    """Stands in for the LLMWatch server and records every request it gets."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response | Exception] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        result = self.responses.pop(0) if self.responses else httpx.Response(200)
        if isinstance(result, Exception):
            raise result
        return result

    def batches(self) -> list[list[dict]]:
        return [json.loads(r.content)["events"] for r in self.requests]


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> FakeServer:
    # Every httpx.Client that LLMWatch builds talks to FakeServer instead of
    # the network, while keeping the real base_url and headers.
    fake = FakeServer()
    real_client = httpx.Client
    monkeypatch.setattr(
        client_module.httpx,
        "Client",
        partial(real_client, transport=httpx.MockTransport(fake.handler)),
    )
    return fake


def make_watch(**kwargs) -> LLMWatch:
    # A long interval keeps the background thread out of the way so each test
    # decides when flush() runs.
    kwargs.setdefault("flush_interval", 3600)
    return LLMWatch(api_key="test-key", host="http://test", **kwargs)


def event(n: int) -> dict:
    return {"id": str(n)}


def test_flush_posts_queued_events(server: FakeServer) -> None:
    watch = make_watch()
    for n in range(3):
        watch.log(event(n))

    watch.flush()

    assert len(server.requests) == 1
    request = server.requests[0]
    assert request.method == "POST"
    assert request.url == "http://test/v1/ingest"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert server.batches() == [[event(0), event(1), event(2)]]


def test_flush_with_empty_queue_sends_nothing(server: FakeServer) -> None:
    watch = make_watch()

    watch.flush()

    assert server.requests == []


def test_flush_caps_request_at_batch_size(server: FakeServer) -> None:
    watch = make_watch(batch_size=50)
    for n in range(120):
        watch.log(event(n))

    watch.flush()

    assert all(len(b) <= 50 for b in server.batches())
    assert server.batches()[0] == [event(n) for n in range(50)]


@pytest.mark.xfail(strict=True, reason="flush() sends only one batch per call")
def test_flush_sends_every_queued_event(server: FakeServer) -> None:
    watch = make_watch(batch_size=50)
    for n in range(120):
        watch.log(event(n))

    watch.flush()

    assert [len(b) for b in server.batches()] == [50, 50, 20]


def test_background_thread_flushes_automatically(server: FakeServer) -> None:
    watch = make_watch(flush_interval=0.05)
    watch.log(event(1))

    deadline = time.monotonic() + 2
    while not server.requests and time.monotonic() < deadline:
        time.sleep(0.01)

    assert server.batches() == [[event(1)]]


def test_log_drops_events_when_queue_is_full(server: FakeServer) -> None:
    watch = make_watch()
    for n in range(10_005):
        watch.log(event(n))  # must not raise

    assert watch.queue.qsize() == 10_000


def test_flush_survives_server_down(server: FakeServer) -> None:
    watch = make_watch()
    server.responses.append(httpx.ConnectError("connection refused"))
    watch.log(event(1))

    watch.flush()  # must not raise

    assert len(server.requests) == 1


def test_flush_survives_server_error_response(server: FakeServer) -> None:
    watch = make_watch()
    server.responses.append(httpx.Response(500))
    watch.log(event(1))

    watch.flush()  # must not raise


@pytest.mark.xfail(strict=True, reason="Phase 10: retry failed batches")
@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("connection refused"), httpx.Response(500)],
    ids=["server-down", "server-500"],
)
def test_failed_batch_is_delivered_once_server_recovers(
    server: FakeServer, failure: httpx.Response | Exception
) -> None:
    watch = make_watch()
    server.responses.append(failure)
    watch.log(event(1))

    watch.flush()  # fails
    watch.flush()  # server is back

    assert len(server.requests) == 2
    assert server.batches()[1] == [event(1)]
