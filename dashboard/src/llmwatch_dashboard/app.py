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


@st.cache_data(ttl=10)
def load_alerts() -> list[dict[str, Any]]:
    return api.fetch_alerts()


def send_feedback(event_id: str) -> None:
    # st.feedback "thumbs": 1 = thumbs up, 0 = thumbs down, None = cleared.
    choice = st.session_state[f"feedback_{event_id}"]
    if choice is None:
        return
    try:
        api.post_feedback(event_id, float(choice))
    except httpx.HTTPError:
        st.session_state.feedback_error = "Couldn't save your feedback."
        return
    load_stats.clear()  # so the quality numbers include the new vote


def remove_alert(rule_id: int) -> None:
    try:
        api.delete_alert(rule_id)
    except httpx.HTTPError:
        st.session_state.alert_error = "Couldn't delete the rule."
        return
    load_alerts.clear()


def metric_label(rule: dict[str, Any]) -> str:
    if rule["metric"] == "avg_score":
        return f"avg {rule['score_name']}"
    return rule["metric"].replace("_", " ")


def fmt_metric(metric: str, value: float | None) -> str:
    """Show each metric in its natural unit: 21.7%, 1702 ms, $0.1750."""
    if value is None:
        return "no data"
    if metric in ("error_rate", "avg_score"):
        return f"{value:.1%}"
    if metric == "avg_latency":
        return f"{value:,.0f} ms"
    return f"${value:.4f}"


def describe_rule(rule: dict[str, Any]) -> str:
    return (
        f"{metric_label(rule)} {rule['op']} "
        f"{fmt_metric(rule['metric'], rule['threshold'])} "
        f"(last {rule['window_minutes']} min)"
    )


st.set_page_config(page_title="LLMWatch", layout="wide")
st.title("LLMWatch")

if st.sidebar.button("Refresh"):
    st.cache_data.clear()

if not api.has_api_key():
    st.error(
        "Start the dashboard with your .env loaded:\n\n"
        "`uv run --env-file .env streamlit run dashboard/src/llmwatch_dashboard/app.py`",
        title="LLMWATCH_API_KEY is not set",
    )
    st.stop()

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

# --- Firing alerts banner -------------------------------------------------
try:
    alerts = load_alerts()
except httpx.HTTPError:
    alerts = []
    st.warning("Couldn't load alert rules.")
for rule in alerts:
    if rule["firing"]:
        st.error(
            f"{metric_label(rule).capitalize()} is "
            f"{fmt_metric(rule['metric'], rule['last_value'])}. "
            f"Rule: {describe_rule(rule)}.",
            title=f"Alert firing: {rule['name']}",
            icon=":material/notifications_active:",
        )

overview_tab, alerts_tab = st.tabs(["Overview", "Alerts"])

with overview_tab:
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

    # --- Quality (eval scores) -------------------------------------------------
    st.subheader("Quality")
    if stats["scores"]:
        with st.container(horizontal=True):
            for score in stats["scores"]:
                st.metric(
                    f"{score['name']} ({score['source']})",
                    f"{score['avg']:.0%}",
                    help=f"Average of {score['count']} scores",
                    border=True,
                )
    else:
        st.info("No scores yet.")

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
    selection = st.dataframe(
        rows,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="events_table",
    )

    # --- Selected event detail -------------------------------------------------
    if not selection.selection.rows:
        st.caption("Select a row to see its input, output and scores.")
    else:
        event = events[selection.selection.rows[0]]
        st.subheader(f"Event {event['id']}")

        left, right = st.columns(2)
        with left:
            st.markdown("**Input**")
            st.json(event["input"], expanded=False)
            st.markdown("**Output**")
            st.code(event["output"] or "", language=None, wrap_lines=True)
            if event["error"]:
                st.error(event["error"], title="Error")

        with right:
            st.markdown("**Scores**")
            try:
                scores = api.fetch_scores(event["id"])
            except httpx.HTTPError:
                st.error("Couldn't load scores for this event.")
                scores = []
            if scores:
                st.dataframe(
                    [
                        {
                            "name": s["name"],
                            "value": s["value"],
                            "source": s["source"],
                            "comment": s["comment"],
                        }
                        for s in scores
                    ],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("No scores for this event yet.")

            st.markdown("**Was this response good?**")
            st.feedback(
                "thumbs",
                key=f"feedback_{event['id']}",
                on_change=send_feedback,
                args=(event["id"],),
            )
            if error := st.session_state.pop("feedback_error", None):
                st.error(error)

# --- Alerts tab ------------------------------------------------------------
METRICS = {
    "error_rate": "Error rate (0-1)",
    "avg_latency": "Avg latency (ms)",
    "total_cost": "Total cost ($)",
    "avg_score": "Avg score (0-1)",
}


def fmt_time(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts) if ts else None


with alerts_tab:
    st.subheader("Alert rules")
    if alerts:
        st.dataframe(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "status": "🔴 firing" if r["firing"] else "✅ ok",
                    "rule": describe_rule(r),
                    "last value": fmt_metric(r["metric"], r["last_value"]),
                    "last checked": fmt_time(r["last_checked_at"]),
                    "last fired": fmt_time(r["last_fired_at"]),
                    "webhook": bool(r["webhook_url"]),
                }
                for r in alerts
            ],
            width="stretch",
            hide_index=True,
        )
        with st.container(horizontal=True, vertical_alignment="bottom"):
            to_delete = st.selectbox(
                "Rule to delete",
                alerts,
                format_func=lambda r: f"#{r['id']} {r['name']}",
            )
            st.button(
                "Delete",
                icon=":material/delete:",
                on_click=remove_alert,
                args=(to_delete["id"],),
            )
    else:
        st.info("No alert rules yet. Create one below.")
    st.caption("Values update when the alerter runs (every minute by default).")

    st.subheader("New rule")
    with st.form("new_alert", clear_on_submit=True):
        name = st.text_input("Name", placeholder="Too many errors")
        metric = st.selectbox("Metric", list(METRICS), format_func=lambda m: METRICS[m])
        c1, c2, c3 = st.columns(3)
        op = c1.segmented_control("Fire when", ["above", "below"], default="above")
        threshold = c2.number_input("Threshold", value=0.1, format="%g")
        window = c3.number_input(
            "Window (minutes)", min_value=1, max_value=1440, value=60
        )
        score_name = st.text_input(
            "Score name (only for avg score)", placeholder="helpfulness"
        )
        webhook = st.text_input(
            "Webhook URL (optional)", placeholder="https://hooks.slack.com/..."
        )
        submitted = st.form_submit_button("Create rule", type="primary")

    if submitted:
        rule = {
            "name": name.strip(),
            "metric": metric,
            "op": op or "above",
            "threshold": threshold,
            "window_minutes": int(window),
            "score_name": score_name.strip() or None,
            "webhook_url": webhook.strip() or None,
        }
        if not rule["name"]:
            st.error("Give the rule a name.")
        else:
            try:
                api.create_alert(rule)
            except httpx.HTTPStatusError as e:
                # 422 = validation error, e.g. avg score without a score name.
                st.error(f"Couldn't create the rule: {e.response.text}")
            except httpx.HTTPError:
                st.error("Couldn't reach the API.")
            else:
                load_alerts.clear()
                st.rerun()

    if error := st.session_state.pop("alert_error", None):
        st.error(error)
