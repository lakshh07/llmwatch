from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import EventRow, get_session
from ..models import ModelStats, StatsOut

router = APIRouter()


@router.get("/stats")
def get_stats(
    session: Annotated[Session, Depends(get_session)],
) -> StatsOut:
    totals_stmt = select(
        func.count(),
        func.sum(EventRow.cost),
        func.avg(EventRow.latency),
        func.count().filter(EventRow.status == "error"),
    )
    total_events, total_cost, avg_latency, error_count = session.execute(
        totals_stmt
    ).one()

    by_model_stmt = (
        select(
            EventRow.model,
            func.count(),
            func.sum(EventRow.cost),
        )
        .group_by(EventRow.model)
        .order_by(func.sum(EventRow.cost).desc())
    )
    by_model = [
        ModelStats(model=model, events=events, cost=cost or 0)
        for model, events, cost in session.execute(by_model_stmt)
    ]

    return StatsOut(
        total_events=total_events or 0,
        total_cost=total_cost or 0,
        avg_latency=avg_latency or 0,
        error_count=error_count or 0,
        by_model=by_model,
    )
