from time import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import AlertRuleRow, get_session
from ..models import AlertRuleIn, AlertRuleOut

router = APIRouter()


@router.post("/alerts", status_code=201)
def create_alert(
    body: AlertRuleIn,
    session: Annotated[Session, Depends(get_session)],
) -> AlertRuleOut:
    rule = AlertRuleRow(**body.model_dump(), created_at=time())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return AlertRuleOut.model_validate(rule)


@router.get("/alerts")
def list_alerts(
    session: Annotated[Session, Depends(get_session)],
) -> list[AlertRuleOut]:
    rows = session.scalars(select(AlertRuleRow).order_by(AlertRuleRow.id)).all()
    return [AlertRuleOut.model_validate(row) for row in rows]


@router.delete("/alerts/{rule_id}", status_code=204)
def delete_alert(
    rule_id: int,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    rule = session.get(AlertRuleRow, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    session.delete(rule)
    session.commit()
