import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from llmwatch_server import migrate
from llmwatch_server.db import Base
from sqlalchemy import Engine, create_engine, inspect


@pytest.fixture
def engine() -> Engine:
    return create_engine("sqlite://")


def run_alembic(engine: Engine, action: str, revision: str) -> None:
    config = migrate.alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        getattr(command, action)(config, revision)


def test_migrations_match_the_models(engine: Engine) -> None:
    """If this fails, you changed db.py without adding a migration:
    uv run alembic -c server/alembic.ini revision --autogenerate -m "..."
    """
    run_alembic(engine, "upgrade", "head")

    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []


def test_migrations_downgrade_to_empty(engine: Engine) -> None:
    run_alembic(engine, "upgrade", "head")
    run_alembic(engine, "downgrade", "base")

    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_check_schema_stops_when_database_is_behind(
    engine: Engine, monkeypatch
) -> None:
    monkeypatch.setattr(migrate, "get_engine", lambda: engine)

    with pytest.raises(SystemExit, match="llmwatch-migrate"):
        migrate.check_schema()

    run_alembic(engine, "upgrade", "head")
    migrate.check_schema()  # up to date: no error
