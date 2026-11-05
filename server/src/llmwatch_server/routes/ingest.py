from fastapi import APIRouter

from ..models import IngestRequest

router = APIRouter()


@router.post("/ingest", status_code=202)
def ingest(body: IngestRequest) -> dict[str, int]:
    return {"accepted": len(body.events)}
