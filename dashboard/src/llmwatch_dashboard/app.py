from datetime import datetime
from typing import Any

import httpx
import streamlit as st

from llmwatch_dashboard import api

ALL = "All"


@st.cache_data(ttl=10)
def load_stats() -> dict[str, Any]:
    return api.fetch_stats()


@st.cache_data(ttl=10)
def load_events(limit: int, model: str | None, status: str | None) -> list[dict]:
    return api.fetch_events(limit=limit, model=model, status=status)


st.set_page_config(page_title="LLMWatch", layout="wide")
st.title("LLMWatch")

if st.sidebar.button("Refresh"):
    st.cache_data.clear()

try:
    stats = load_stats()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 401:
        st.error("API key rejected. Start the dashboard with LLMWATCH_API_KEY set.")
    else:
        st.error(f"API returned an error: {e.response.status_code}")
    st.stop()
except httpx.HTTPError:
    st.error("Can't reach the LLMWatch API. Is the server running on port 8000?")
    st.stop()

# --- Sidebar filters -------------------------------------------------------
st.sidebar.header("Filters")
model_choices = [ALL] + [m["model"] for m in stats["by_model"] if m["model"]]
model_pick = st.sidebar.selectbox("Model", model_choices)
status_pick = st.sidebar.selectbox("Status", [ALL, "ok", "error", "incomplete"])
limit = st.sidebar.slider("Max events", min_value=10, max_value=500, value=50)

# --- Top numbers -----------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Events", stats["total_events"])
c2.metric("Total cost", f"${stats['total_cost']:.4f}")
c3.metric("Avg latency", f"{stats['avg_latency']:.0f} ms")
c4.metric("Errors", stats["error_count"])

# --- Cost per model --------------------------------------------------------
st.subheader("Cost by model")
if stats["by_model"]:
    st.bar_chart({(m["model"] or "unknown"): m["cost"] for m in stats["by_model"]})
else:
    st.info("No events yet.")

# --- Recent events ---------------------------------------------------------
st.subheader("Recent events")
events = load_events(
    limit,
    None if model_pick == ALL else model_pick,
    None if status_pick == ALL else status_pick,
)
rows = [
    {
        "time": datetime.fromtimestamp(e["start_time"]),
        "model": e["model"],
        "status": e["status"],
        "latency_ms": e["latency"],
        "input_tokens": e["input_tokens"],
        "output_tokens": e["output_tokens"],
        "cost": e["cost"],
        "id": e["id"],
    }
    for e in events
]
st.dataframe(rows, width="stretch")
