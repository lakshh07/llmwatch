import pytest
from llmwatch import wrap_openai

from tests.helpers import FakeLLMWatch, FakeOpenAIClient, fake_openai_response

MESSAGES = [{"role": "user", "content": "Hello"}]


def test_openai_wrapper_log_events():
    client = FakeOpenAIClient()
    llmwatch = FakeLLMWatch()

    wrapped_client = wrap_openai(client, llmwatch)

    wrapped_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Hello"},
        ],
    )

    assert len(llmwatch.events) == 1
    assert llmwatch.events[0]["status"] == "ok"
    assert llmwatch.events[0]["model"] == "gpt-4o"
    assert llmwatch.events[0]["output"] == "Test response"


def test_records_input_and_tokens():
    client = FakeOpenAIClient(
        response=fake_openai_response(input_tokens=42, output_tokens=7)
    )
    watch = FakeLLMWatch()

    wrap_openai(client, watch).chat.completions.create(
        model="gpt-4o", messages=MESSAGES
    )

    event = watch.events[0]
    assert event["type"] == "generation"
    assert event["input"] == MESSAGES
    assert event["input_tokens"] == 42
    assert event["output_tokens"] == 7


def test_records_latency_and_timestamps():
    client = FakeOpenAIClient(delay=0.02)
    watch = FakeLLMWatch()

    wrap_openai(client, watch).chat.completions.create(
        model="gpt-4o", messages=MESSAGES
    )

    event = watch.events[0]
    assert isinstance(event["latency"], int)
    assert event["latency"] >= 20
    assert event["end_time"] >= event["start_time"]


def test_returns_response_and_passes_arguments_through():
    client = FakeOpenAIClient()
    watch = FakeLLMWatch()

    res = wrap_openai(client, watch).chat.completions.create(
        model="gpt-4o", messages=MESSAGES, temperature=0.2
    )

    assert res is client.response
    assert client.calls == [
        {"model": "gpt-4o", "messages": MESSAGES, "temperature": 0.2}
    ]


def test_records_error_and_reraises():
    client = FakeOpenAIClient(error=RuntimeError("rate limited"))
    watch = FakeLLMWatch()

    with pytest.raises(RuntimeError, match="rate limited"):
        wrap_openai(client, watch).chat.completions.create(
            model="gpt-4o", messages=MESSAGES
        )

    assert len(watch.events) == 1
    event = watch.events[0]
    assert event["status"] == "error"
    assert event["error"] == "rate limited"
    assert event["model"] == "gpt-4o"
    assert "latency" in event
    assert "output" not in event


def test_streaming_call_does_not_crash_user_app():
    client = FakeOpenAIClient(response=["streamed chunk 1", "streamed chunk 2"])
    watch = FakeLLMWatch()

    res = wrap_openai(client, watch).chat.completions.create(
        model="gpt-4o", messages=MESSAGES, stream=True
    )

    assert res is client.response
    assert client.calls == [{"model": "gpt-4o", "messages": MESSAGES, "stream": True}]
    assert len(watch.events) == 1
    event = watch.events[0]
    assert event["status"] == "ok"
    assert "parse_error" in event
