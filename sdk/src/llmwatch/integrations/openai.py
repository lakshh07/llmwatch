import time
import uuid


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
        }

        try:
            try:
                res = original(*args, **kwargs)
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
            event["latency"] = round((time.perf_counter() - start) * 1000)
            event["end_time"] = time.time()
            watch.log(event)

    client.chat.completions.create = create
    return client
