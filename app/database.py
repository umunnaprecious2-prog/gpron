import sys
from typing import AsyncGenerator

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


def connect_args() -> dict:
    # Neon (and most hosted Postgres) requires SSL. asyncpg wants ssl=True/
    # "require" passed as a connect kwarg, not the libpq-style "sslmode"
    # query param, so we set it explicitly here instead of relying on the
    # connection string. Skip it for local/Docker Postgres, which has no TLS.
    # Reused by migrations/env.py so Alembic connects the same way.
    if "neon.tech" in settings.database_url:
        return {"ssl": "require"}
    return {}


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
