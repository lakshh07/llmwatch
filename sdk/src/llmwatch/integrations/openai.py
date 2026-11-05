import time
import uuid


def _watch_stream(stream, event, start, watch, user_wants_usage=False):
    pieces: list[str] = []

    try:
        for chunk in stream:
            if chunk.choices:
                try:
                    content = chunk.choices[0].delta.content
                    if content is not None:
                        if not pieces:  # bonus: first text piece = time to first token
                            event["ttft"] = round((time.perf_counter() - start) * 1000)
                        pieces.append(content)

                except (AttributeError, IndexError, TypeError) as e:
                    event["parse_error"] = str(e)

            if chunk.usage:
                event.update(
                    input_tokens=chunk.usage.prompt_tokens,
                    output_tokens=chunk.usage.completion_tokens,
                )

            if chunk.choices and chunk.choices[0].finish_reason:
                event.update(status="ok")

            if not user_wants_usage and chunk.usage and not chunk.choices:
                continue

            yield chunk
    finally:
        event["output"] = "".join(pieces)
        event["latency"] = round((time.perf_counter() - start) * 1000)
        event["end_time"] = time.time()
        watch.log(event)


def wrap_openai(client, watch):
    original = client.chat.completions.create

    def create(*args, **kwargs):
        start = time.perf_counter()
        event = {
            "id": uuid.uuid4().hex,
            "type": "generation",
            "model": kwargs.get("model"),
            "input": kwargs.get("messages"),
            "start_time": time.time(),
            "status": "incomplete",
        }

        streaming = False
        user_wants_usage = False

        if kwargs.get("stream"):
            opts = kwargs.get("stream_options") or {}
            user_wants_usage = opts.get("include_usage", False)
            kwargs["stream_options"] = {**opts, "include_usage": True}

        try:
            try:
                res = original(*args, **kwargs)
                if kwargs.get("stream"):
                    streaming = True
                    return _watch_stream(res, event, start, watch, user_wants_usage)
            except Exception as e:
                # If the original call raises an exception, we still want to log it
                event.update(status="error", error=str(e))
                raise  # Re-raise the exception after logging it

            try:
                event.update(
                    output=res.choices[0].message.content,
                    input_tokens=res.usage.prompt_tokens,
                    output_tokens=res.usage.completion_tokens,
                )
            except (AttributeError, IndexError, TypeError) as e:
                event["parse_error"] = str(e)

            event.update(status="ok")
            return res
        finally:
            if not streaming:
                event["latency"] = round((time.perf_counter() - start) * 1000)
                event["end_time"] = time.time()
                watch.log(event)

    client.chat.completions.create = create
    return client
