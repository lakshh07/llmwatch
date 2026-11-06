from fastapi import Depends, FastAPI

from .auth import require_api_key
from .routes import health, ingest


def create_app() -> FastAPI:
    app = FastAPI(title="LLMWatch")
    app.include_router(health.router)
    app.include_router(
        ingest.router,
        prefix="/v1",
        tags=["Ingest"],
        dependencies=[Depends(require_api_key)],
    )
    return app
