"""Alembic migration environment — async mode (asyncpg / SQLAlchemy asyncio).

DATABASE_URL is read lazily from the environment inside the migration functions.
This allows `alembic/env.py` to import cleanly without the env var set, which keeps
the test suite green (no live Postgres is needed until `alembic upgrade head` is run).

Usage:
    DATABASE_URL=postgresql+asyncpg://user:pass@host/db uv run alembic upgrade head
    DATABASE_URL=...                                    uv run alembic downgrade -1
    DATABASE_URL=...                                    uv run alembic revision --autogenerate -m "..."

See ADR-013 for the rationale behind the async migration pattern and lazy URL read.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Alembic config object — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Set up Python logging as declared in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# target_metadata
# T003 will import the SQLAlchemy MetaData here to enable autogenerate support.
# ---------------------------------------------------------------------------
target_metadata = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_url() -> str:
    """Read DATABASE_URL from the environment.

    Called lazily (inside migration functions only) so importing this module
    does not raise when the env var is absent (e.g. during `uv run pytest`).

    Raises RuntimeError with a clear message if DATABASE_URL is not set,
    so a missing env var is an obvious failure rather than a cryptic SQLAlchemy
    error later.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it before running alembic commands.\n"
            "Example: DATABASE_URL=postgresql+asyncpg://user:pass@host/db "
            "uv run alembic upgrade head"
        )
    return url


# ---------------------------------------------------------------------------
# Offline mode — generates SQL script without a live DB connection
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in offline mode.

    Configures the context with a URL rather than a live Engine.
    Useful for generating SQL scripts (e.g. `alembic upgrade head --sql`).
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — uses an async engine + asyncpg driver
# ---------------------------------------------------------------------------

def do_run_migrations(connection) -> None:
    """Synchronous callback that Alembic runs inside an async connection.

    `connection.run_sync(do_run_migrations)` bridges the async/sync boundary.
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in online mode against a live Postgres database.

    Creates an AsyncEngine, opens a connection, runs migrations synchronously
    inside `connection.run_sync`, then disposes the engine.  NullPool is used
    because migration scripts are short-lived one-shot processes.
    """
    from sqlalchemy.pool import NullPool

    url = _get_url()
    connectable = create_async_engine(url, poolclass=NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# ---------------------------------------------------------------------------
# Entry point — called by Alembic CLI
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
