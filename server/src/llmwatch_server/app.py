from fastapi import FastAPI

from .routes import health


def create_app() -> FastAPI:
    app = FastAPI(title="LLMWatch")
    app.include_router(health.router)
    return app
