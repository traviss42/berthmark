"""Asynchronous database engine and session management for Berthmark."""

import os
from collections.abc import AsyncGenerator
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from backend.models import Base

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./berthmark.db"


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforce foreign key constraints on SQLite connections."""
    if hasattr(dbapi_connection, "cursor"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_database_url() -> str:
    """Retrieve and normalize database URL from environment."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("sqlite:///"):
        # Normalize sqlite:/// to sqlite+aiosqlite:///
        url = "sqlite+aiosqlite:///" + url[len("sqlite:///"):]
    return url


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = get_database_url()
        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create singleton async sessionmaker."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session that commits on success and rolls back on exception."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def ping_database() -> bool:
    """Test connectivity by executing SELECT 1 on the database."""
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        scalar = result.scalar()
        return scalar == 1


async def reset_engine() -> None:
    """Dispose active engine and reset singletons (useful for test isolation)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
