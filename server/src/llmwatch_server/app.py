from fastapi import FastAPI

from .routes import health, ingest


def create_app() -> FastAPI:
    app = FastAPI(title="LLMWatch")
    app.include_router(health.router)
    app.include_router(ingest.router, prefix="/v1", tags=["Ingest"])
    return app
