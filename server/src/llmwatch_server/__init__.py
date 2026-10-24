import uvicorn


def main() -> None:
    uvicorn.run("llmwatch_server.app:create_app", factory=True, port=8000)
