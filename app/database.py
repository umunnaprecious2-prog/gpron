import sys
from typing import AsyncGenerator
from urllib.parse import urlsplit

from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


async def _skip_json_codec(self, conn) -> None:
    """No-op replacement for SQLAlchemy's asyncpg dialect json codec setup.

    On every new connection, SQLAlchemy tries to register asyncpg codecs for
    both the "json" and "jsonb" Postgres types. CockroachDB has no distinct
    "json" type (only "jsonb"), so that lookup fails with
    ValueError: unknown type: pg_catalog.json on every connection attempt.
    Our schema only ever uses JSONB columns (see app/models/db.py), never
    plain JSON, so skipping this codec is safe regardless of which Postgres
    provider is in use.
    """


PGDialect_asyncpg.setup_asyncpg_json_codec = _skip_json_codec


# Hosts that run without TLS: local installs and the docker-compose
# 'postgres' service (reachable as 'postgres' from other containers, or
# 'localhost'/'127.0.0.1' from the host machine). Anything else is assumed
# to be a hosted provider (Neon, CockroachDB, Supabase, RDS, ...) that
# requires SSL, so this generalizes across providers instead of
# special-casing one host.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres"}


def connect_args() -> dict:
    # asyncpg wants ssl=True/"require" passed as a connect kwarg, not the
    # libpq-style "sslmode" query param, so we set it explicitly here
    # instead of relying on the connection string. Reused by
    # migrations/env.py so Alembic connects the same way.
    host = urlsplit(settings.database_url).hostname or ""
    if host in _LOCAL_HOSTS:
        return {}
    return {"ssl": "require"}


# Under pytest, each test function can get its own asyncio event loop
# (pytest-asyncio's default), but a pooled connection stays bound to the
# loop it was opened on. Reusing a pooled connection across a loop switch
# crashes asyncpg ("attached to a different loop"). NullPool sidesteps this
# by never reusing a connection: every checkout opens a fresh one. Pooling
# stays on for the real app.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=connect_args(),
    poolclass=NullPool if "pytest" in sys.modules else None,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def connect_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Connected to Postgres")


async def close_db() -> None:
    await engine.dispose()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
