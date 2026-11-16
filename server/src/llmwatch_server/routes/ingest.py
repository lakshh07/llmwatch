from typing import Annotated

import redis
from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings, get_settings
from ..models import IngestRequest
from ..redis_client import get_redis

router = APIRouter()


@router.post("/ingest", status_code=202)
def ingest(
    body: IngestRequest,
    config: Annotated[Settings, Depends(get_settings)],
    r: Annotated[redis.Redis, Depends(get_redis)],
) -> dict[str, int]:
    pipe = r.pipeline()

    for event in body.events:
        pipe.xadd(
            config.stream_name,
            {"data": event.model_dump_json()},
            maxlen=config.stream_maxlen,
        )

    try:
        pipe.execute()
    except redis.ConnectionError as e:
        raise HTTPException(status_code=503, detail="Redis connection error") from e

    return {"accepted": len(body.events)}
