from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.database.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

dsn = os.getenv("CHAIN_SCOPE_POSTGRES_DSN", "").strip()
if not dsn:
    raise RuntimeError("Set CHAIN_SCOPE_POSTGRES_DSN before running Alembic migrations")
if dsn.startswith("postgresql://"):
    dsn = "postgresql+asyncpg://" + dsn[len("postgresql://"):]
config.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=dsn, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async_migrations())
