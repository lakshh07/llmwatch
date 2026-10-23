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
            res = original(*args, **kwargs)
            event.update(
                status="ok",
                output=res.choices[0].message.content,
                input_tokens=res.usage.prompt_tokens,
                output_tokens=res.usage.completion_tokens,
            )

            return res
        except Exception as e:
            event.update(status="error", error=str(e))
            raise  # Re-raise the exception after logging it, users' error
        finally:
            event["latency"] = round((time.perf_counter() - start) * 1000)
            event["end_time"] = time.time()
            watch.log(event)

    client.chat.completions.create = create
    return client
