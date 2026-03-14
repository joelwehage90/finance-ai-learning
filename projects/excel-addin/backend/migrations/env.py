"""Alembic migration environment — async-aware with autogenerate support.

Uses the same database URL as the application (via config.py) and
imports all models so Alembic can detect schema changes automatically.
"""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure the backend package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from db import Base  # noqa: E402

# Import all models so Base.metadata contains their tables.
import models  # noqa: E402, F401

# Alembic Config object.
config = context.config

# Set the database URL from our app settings (overrides alembic.ini).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Set up Python logging from the config file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our models' metadata for autogenerate.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a live DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using an existing connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (async) migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
