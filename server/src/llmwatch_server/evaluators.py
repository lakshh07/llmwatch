import json
from collections.abc import Callable
from time import time
from typing import Any


def not_empty(event: dict[str, Any]) -> float:
    output = event.get("output") or ""
    return 1.0 if output.strip() else 0.0


def valid_json(event: dict[str, Any]) -> float | None:
    output = (event.get("output") or "").strip()
    if not output.startswith(("{", "[")):
        return None

    try:
        json.loads(output)
    except json.JSONDecodeError:
        return 0.0
    return 1.0


def fast(event: dict[str, Any]) -> float:
    return 1.0 if event["latency"] < 2000 else 0.0


RULES: dict[str, Callable[[dict[str, Any]], float | None]] = {
    "not_empty": not_empty,
    "valid_json": valid_json,
    "fast": fast,
}


def run_rules(event: dict[str, Any]) -> list[dict[str, Any]]:
    if event.get("status") != "ok":
        return []

    scores = []
    for name, rule in RULES.items():
        value = rule(event)
        if value is None:
            continue
        scores.append(
            {
                "event_id": event["id"],
                "name": name,
                "value": value,
                "source": "heuristic",
                "comment": None,
                "created_at": time(),
            }
        )
    return scores
