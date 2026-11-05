import time
from types import SimpleNamespace
from typing import Any


class FakeLLMWatch:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def log(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class FakeOpenAIClient:
    def __init__(
        self,
        response: Any | None = None,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = response or fake_openai_response()
        self.error = error
        self.delay = delay
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        time.sleep(self.delay)

        if self.error is not None:
            raise self.error

        return self.response


def fake_openai_response(
    output: str = "Test response",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Any:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=output),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        ),
    )


class FakeAnthropicClient:
    def __init__(
        self,
        response: Any | None = None,
        error: Exception | None = None,
        delay: float = 0,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = response or fake_anthropic_response()
        self.error = error
        self.delay = delay
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        time.sleep(self.delay)

        if self.error is not None:
            raise self.error

        return self.response


def fake_anthropic_response(
    texts: tuple[str, ...] = ("Test response",),
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Any:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=t) for t in texts],
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


def fake_anthropic_stream():
    response = ["hello", " world", " this", " is", " a", " test"]
    events: list[SimpleNamespace] = [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(usage=SimpleNamespace(input_tokens=10)),
        )
    ]
    for word in response:
        events.append(
            SimpleNamespace(
                type="content_block_delta", delta=SimpleNamespace(text=word)
            )
        )

    events.append(
        SimpleNamespace(
            type="message_delta", usage=SimpleNamespace(output_tokens=len(response))
        )
    )
    events.append(SimpleNamespace(type="message_stop"))

    return events
