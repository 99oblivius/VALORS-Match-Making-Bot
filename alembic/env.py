import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from alembic import context
from src.utils.models import Base

config = context.config

fileConfig(config.config_file_name)

if 'DATABASE_URL' in os.environ:
    config.set_main_option('sqlalchemy.url', os.environ['DATABASE_URL'])
else: raise Exception("DATABASE_URL environment variable is not set.")

target_metadata = Base.metadata

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

def run_migrations_online():
    """Run migrations in 'online' mode."""
    import asyncio
    asyncio.run(run_async_migrations())

run_migrations_online()
