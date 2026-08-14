import pytest_asyncio

from app.database import Base, engine

# Import registers the ORM models on Base.metadata, needed for create_all.
from app.models import db as db_models  # noqa: F401


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """Postgres needs tables to exist before tests run (Mongo collections
    were created implicitly). Runs once per test session against whatever
    DATABASE_URL is configured (local Docker Postgres by default)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
