import time
import uuid


def _watch_stream(stream, event, start, watch):
    pieces: list[str] = []

    try:
        for block in stream:
            if block.type == "message_start":
                event["input_tokens"] = getattr(
                    block.message.usage, "input_tokens", None
                )
            elif block.type == "content_block_delta":
                if not pieces:  # bonus: first text piece = time to first token
                    event["ttft"] = round((time.perf_counter() - start) * 1000)
                pieces.append(getattr(block.delta, "text", ""))
            elif block.type == "message_delta":
                event["output_tokens"] = getattr(block.usage, "output_tokens", None)
            elif block.type == "message_stop":
                event.update(status="ok")
            yield block
    finally:
        event["output"] = "".join(pieces)
        event["latency"] = round((time.perf_counter() - start) * 1000)
        event["end_time"] = time.time()
        watch.log(event)


def wrap_anthropic(client, watch):
    original = client.messages.create

    def create(*args, **kwargs):
        start = time.perf_counter()
        event = {
            "id": uuid.uuid4().hex,
            "type": "generation",
            "model": kwargs.get("model"),
            "input": {
                "system": kwargs.get("system"),
                "messages": kwargs.get("messages"),
            },
            "start_time": time.time(),
            "status": "incomplete",
        }

        streaming = False
        try:
            try:
                res = original(*args, **kwargs)
                if kwargs.get("stream"):
                    streaming = True
                    return _watch_stream(res, event, start, watch)
            except Exception as e:
                # If the original call raises an exception, we still want to log it
                event.update(status="error", error=str(e))
                raise  # Re-raise the exception after logging it

            try:
                output = "\n".join(
                    block.text for block in res.content if block.type == "text"
                )

                event.update(
                    output=output,
                    input_tokens=res.usage.input_tokens,
                    output_tokens=res.usage.output_tokens,
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

    client.messages.create = create
    return client
