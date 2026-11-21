from logging.config import fileConfig

from alembic import context
from llmwatch_server.config import get_settings
from llmwatch_server.db import Base
from sqlalchemy import Connection, create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Compare migrations against our SQLAlchemy models (used by --autogenerate).
target_metadata = Base.metadata


def run_on(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things; batch mode copies the table instead.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Tests hand us an open connection; everyone else uses the configured URL.
    connection = config.attributes.get("connection")
    if connection is not None:
        run_on(connection)
        return

    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        run_on(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
