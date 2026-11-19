from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import EventRow, get_session
from ..models import EventOut

router = APIRouter()


@router.get("/events")
def list_events(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    model: str | None = None,
    status: str | None = None,
) -> list[EventOut]:
    stmt = select(EventRow).order_by(EventRow.start_time.desc()).limit(limit)

    if model is not None:
        stmt = stmt.where(EventRow.model == model)
    if status is not None:
        stmt = stmt.where(EventRow.status == status)

    return [EventOut.model_validate(row) for row in session.scalars(stmt).all()]
