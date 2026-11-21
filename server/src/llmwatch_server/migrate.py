from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from .db import get_engine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config() -> Config:
    # Built in code (not from alembic.ini) so it also works inside the Docker
    # image, where only the installed package is available.
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def check_schema() -> None:
    """Stop with a clear message if the database is behind the code.

    The worker and alerter call this on startup instead of creating tables
    themselves, so schema changes only ever happen through migrations.
    """
    with get_engine().connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if current != head:
        raise SystemExit(
            f"Database schema is at revision {current}, but the code expects {head}. "
            "Run: uv run llmwatch-migrate"
        )


def main() -> None:
    """Bring the database schema up to date: `uv run llmwatch-migrate`."""
    command.upgrade(alembic_config(), "head")
    print("Database is up to date.")


if __name__ == "__main__":
    main()
