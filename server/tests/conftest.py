import pytest
from fastapi.testclient import TestClient
from llmwatch_server.app import create_app
from llmwatch_server.config import Settings, get_settings


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides = {
        get_settings: lambda: Settings(
            api_key="test-key", database_url="sqlite:///test.db"
        )
    }

    return TestClient(app)
