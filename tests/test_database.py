"""Unit and integration tests for async database engine and connectivity."""

import os
import pytest
from sqlalchemy import text
from backend.database import (
    DEFAULT_DATABASE_URL,
    get_database_url,
    get_engine,
    get_db_session,
    ping_database,
)


def test_get_database_url_default(monkeypatch):
    """Verify default database URL when unset or empty."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert get_database_url() == DEFAULT_DATABASE_URL

    monkeypatch.setenv("DATABASE_URL", "")
    assert get_database_url() == DEFAULT_DATABASE_URL


def test_get_database_url_normalization(monkeypatch):
    """Verify sqlite:/// is normalized to sqlite+aiosqlite:///."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    assert get_database_url() == "sqlite+aiosqlite:///test.db"

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///custom.db")
    assert get_database_url() == "sqlite+aiosqlite:///custom.db"


@pytest.mark.asyncio
async def test_ping_database():
    """Verify ping_database executes SELECT 1 and returns True."""
    healthy = await ping_database()
    assert healthy is True


@pytest.mark.asyncio
async def test_get_db_session():
    """Verify get_db_session yields an active session capable of executing queries."""
    async for session in get_db_session():
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
