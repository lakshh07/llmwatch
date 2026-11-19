import os
from typing import Any

import httpx


def _base_url() -> str:
    return os.environ.get("LLMWATCH_API_URL", "http://localhost:8000")


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
