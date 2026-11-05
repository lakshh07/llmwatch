import time
import uuid


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
        }

        try:
            try:
                res = original(*args, **kwargs)
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
            event["latency"] = round((time.perf_counter() - start) * 1000)
            event["end_time"] = time.time()
            watch.log(event)

    client.messages.create = create
    return client
