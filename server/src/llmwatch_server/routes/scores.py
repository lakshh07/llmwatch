from time import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import EventRow, ScoreRow, get_session
from ..models import ScoreIn, ScoreOut

router = APIRouter()


@router.post("/events/{event_id}/scores", status_code=201)
def create_score(
    event_id: str,
    body: ScoreIn,
    session: Annotated[Session, Depends(get_session)],
) -> ScoreOut:
    event = session.get(EventRow, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    score = ScoreRow(
        event_id=event_id,
        name=body.name,
        value=body.value,
        source=body.source,
        comment=body.comment,
        created_at=time(),
    )
    session.add(score)
    session.commit()
    session.refresh(score)
    return ScoreOut.model_validate(score)


@router.get("/events/{event_id}/scores")
def list_scores(
    event_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> list[ScoreOut]:
    stmt = (
        select(ScoreRow)
        .where(ScoreRow.event_id == event_id)
        .order_by(ScoreRow.created_at)
    )
    return [ScoreOut.model_validate(row) for row in session.scalars(stmt).all()]
