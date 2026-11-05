from types import SimpleNamespace

import pytest
from llmwatch import wrap_anthropic

from tests.helpers import (
    FakeAnthropicClient,
    FakeLLMWatch,
    fake_anthropic_response,
    fake_anthropic_stream,
)

MODEL = "claude-opus-5-5"
MESSAGES = [{"role": "user", "content": "Hello"}]


def test_records_successful_call():
    client = FakeAnthropicClient(
        response=fake_anthropic_response(input_tokens=42, output_tokens=7)
    )
    watch = FakeLLMWatch()

    wrap_anthropic(client, watch).messages.create(
        model=MODEL, system="Be brief", messages=MESSAGES, max_tokens=100
    )

    assert len(watch.events) == 1
    event = watch.events[0]
    assert event["type"] == "generation"
    assert event["status"] == "ok"
    assert event["model"] == MODEL
    assert event["input"] == {"system": "Be brief", "messages": MESSAGES}
    assert event["output"] == "Test response"
    assert event["input_tokens"] == 42
    assert event["output_tokens"] == 7


def test_joins_text_blocks_and_skips_others():
    response = fake_anthropic_response(texts=("Hello", "world"))
    response.content.insert(1, SimpleNamespace(type="tool_use", name="search"))
    client = FakeAnthropicClient(response=response)
    watch = FakeLLMWatch()

    wrap_anthropic(client, watch).messages.create(model=MODEL, messages=MESSAGES)

    assert watch.events[0]["output"] == "Hello\nworld"


def test_records_latency_and_timestamps():
    client = FakeAnthropicClient(delay=0.02)
    watch = FakeLLMWatch()

    wrap_anthropic(client, watch).messages.create(model=MODEL, messages=MESSAGES)

    event = watch.events[0]
    assert isinstance(event["latency"], int)
    assert event["latency"] >= 20
    assert event["end_time"] >= event["start_time"]


def test_returns_response_and_passes_arguments_through():
    client = FakeAnthropicClient()
    watch = FakeLLMWatch()

    res = wrap_anthropic(client, watch).messages.create(
        model=MODEL, messages=MESSAGES, max_tokens=100
    )

    assert res is client.response
    assert client.calls == [{"model": MODEL, "messages": MESSAGES, "max_tokens": 100}]


def test_records_error_and_reraises():
    client = FakeAnthropicClient(error=RuntimeError("overloaded"))
    watch = FakeLLMWatch()

    with pytest.raises(RuntimeError, match="overloaded"):
        wrap_anthropic(client, watch).messages.create(model=MODEL, messages=MESSAGES)

    assert len(watch.events) == 1
    event = watch.events[0]
    assert event["status"] == "error"
    assert event["error"] == "overloaded"
    assert event["model"] == MODEL
    assert "latency" in event
    assert "output" not in event


def test_records_streaming_output():
    client = FakeAnthropicClient(response=fake_anthropic_stream())
    watch = FakeLLMWatch()

    res = wrap_anthropic(client, watch).messages.create(
        model=MODEL, messages=MESSAGES, stream=True
    )

    assert len(watch.events) == 0
    list(res)
    assert len(watch.events) == 1

    event = watch.events[0]
    assert event["status"] == "ok"
    assert event["output"] == "hello world this is a test"
    assert event["input_tokens"] == 10
    assert event["output_tokens"] == 6
    assert "ttft" in event
