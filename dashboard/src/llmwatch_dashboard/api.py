import os
from typing import Any

import httpx


def _base_url() -> str:
    return os.environ.get("LLMWATCH_API_URL", "http://localhost:8000")


def has_api_key() -> bool:
    return bool(os.environ.get("LLMWATCH_API_KEY"))


def _headers() -> dict[str, str]:
    api_key = os.environ.get("LLMWATCH_API_KEY", "")
    return {"Authorization": f"Bearer {api_key}"}


def fetch_stats() -> dict[str, Any]:
    response = httpx.get(f"{_base_url()}/v1/stats", headers=_headers(), timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_events(
    limit: int = 50,
    model: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    # httpx sends None as an empty string (?model=), which the API treats as
    # "model must equal ''". Drop the filters that aren't set.
    params = {
        key: value
        for key, value in {"limit": limit, "model": model, "status": status}.items()
        if value is not None
    }
    response = httpx.get(
        f"{_base_url()}/v1/events", params=params, headers=_headers(), timeout=5
    )
    response.raise_for_status()
    return response.json()


def fetch_scores(event_id: str) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{_base_url()}/v1/events/{event_id}/scores", headers=_headers(), timeout=5
    )
    response.raise_for_status()
    return response.json()


def post_feedback(event_id: str, value: float) -> None:
    """Save a human 👍 (1.0) / 👎 (0.0) as a score on the event."""
    response = httpx.post(
        f"{_base_url()}/v1/events/{event_id}/scores",
        json={"name": "user_feedback", "value": value, "source": "human"},
        headers=_headers(),
        timeout=5,
    )
    response.raise_for_status()


def fetch_alerts() -> list[dict[str, Any]]:
    response = httpx.get(f"{_base_url()}/v1/alerts", headers=_headers(), timeout=5)
    response.raise_for_status()
    return response.json()


def create_alert(rule: dict[str, Any]) -> None:
    response = httpx.post(
        f"{_base_url()}/v1/alerts", json=rule, headers=_headers(), timeout=5
    )
    response.raise_for_status()


def delete_alert(rule_id: int) -> None:
    response = httpx.delete(
        f"{_base_url()}/v1/alerts/{rule_id}", headers=_headers(), timeout=5
    )
    response.raise_for_status()
