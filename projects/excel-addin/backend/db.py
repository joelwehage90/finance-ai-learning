"""Database connection management using SQLAlchemy async + asyncpg.

Provides the async engine, session factory, and base model class for
the multi-tenant OAuth token storage.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import get_settings

engine = create_async_engine(get_settings().database_url, echo=False)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields a database session."""
    async with async_session() as session:
        yield session
