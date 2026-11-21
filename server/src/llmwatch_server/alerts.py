from collections.abc import Callable
from typing import Any

import httpx2
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import AlertRuleRow, EventRow, ScoreRow

# send(url, payload) — the real one posts a webhook; tests pass a fake.
Sender = Callable[[str, dict[str, Any]], None]


def compute_metric(session: Session, rule: AlertRuleRow, now: float) -> float | None:
    """The rule's metric over the last `window_minutes`. None = no data."""
    since = now - rule.window_minutes * 60
    in_window = EventRow.start_time >= since

    if rule.metric == "error_rate":
        total, errors = session.execute(
            select(func.count(), func.count().filter(EventRow.status == "error")).where(
                in_window
            )
        ).one()
        return errors / total if total else None

    if rule.metric == "avg_latency":
        return session.scalar(select(func.avg(EventRow.latency)).where(in_window))

    if rule.metric == "total_cost":
        # No events in the window means we spent nothing, so 0 (not "no data").
        return session.scalar(select(func.sum(EventRow.cost)).where(in_window)) or 0.0

    if rule.metric == "avg_score":
        return session.scalar(
            select(func.avg(ScoreRow.value)).where(
                ScoreRow.name == rule.score_name, ScoreRow.created_at >= since
            )
        )

    raise ValueError(f"Unknown metric: {rule.metric}")


def is_breached(rule: AlertRuleRow, value: float | None) -> bool:
    if value is None:
        return False
    if rule.op == "above":
        return value > rule.threshold
    return value < rule.threshold


def format_message(rule: AlertRuleRow, value: float | None, firing: bool) -> str:
    what = rule.metric if rule.metric != "avg_score" else f"avg {rule.score_name}"
    if firing:
        return (
            f"🔴 [LLMWatch] {rule.name}: {what} is {value:.4g} "
            f"({rule.op} {rule.threshold:g}, last {rule.window_minutes} min)"
        )
    if value is None:  # e.g. no traffic in the window any more
        return f"✅ [LLMWatch] {rule.name} resolved: no {what} data in the window"
    return f"✅ [LLMWatch] {rule.name} resolved: {what} is back to {value:.4g}"


def send_webhook(url: str, payload: dict[str, Any]) -> None:
    # A broken webhook must not stop the alerter from checking other rules.
    try:
        httpx2.post(url, json=payload, timeout=5).raise_for_status()
    except httpx2.HTTPError as e:
        print(f"Webhook to {url} failed: {e}")


def check_rules(session: Session, now: float, send: Sender = send_webhook) -> int:
    """Check every enabled rule once. Returns how many notifications were sent.

    We notify only when a rule *changes* state (ok -> firing, firing -> ok),
    so a rule that stays broken for an hour doesn't spam you every minute.
    The caller commits the session.
    """
    sent = 0
    rules = session.scalars(select(AlertRuleRow).where(AlertRuleRow.enabled)).all()
    for rule in rules:
        value = compute_metric(session, rule, now)
        breached = is_breached(rule, value)
        rule.last_value = value
        rule.last_checked_at = now

        if breached == rule.firing:
            continue  # no change

        rule.firing = breached
        if breached:
            rule.last_fired_at = now
        message = format_message(rule, value, breached)
        print(message)
        if rule.webhook_url:
            send(rule.webhook_url, {"text": message})  # Slack-compatible body
            sent += 1
    return sent
