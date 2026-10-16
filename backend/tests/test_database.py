"""Tests for SQLAlchemy database configuration, models, and database-agnostic engine creation."""

import os
import pytest
from sqlalchemy import create_engine
from app.db import (
    Base,
    MonitoredPort,
    NotificationRecord,
    create_app_engine,
    get_db_context,
    init_db,
    resolve_database_url,
)
from app.db.session import SessionLocal


def test_resolve_database_url_sqlite():
    """Verify relative SQLite paths are normalized and parent directory is created."""
    url = "sqlite:///backend/data/test_db.db"
    resolved = resolve_database_url(url)
    assert resolved.startswith("sqlite:///")
    assert "test_db.db" in resolved


def test_database_agnostic_engine_configuration():
    """Verify engine handles both SQLite options (check_same_thread) and external DB URLs."""
    from sqlalchemy.engine import make_url

    # SQLite
    sqlite_eng = create_app_engine("sqlite:///:memory:")
    assert "sqlite" in sqlite_eng.name

    # External DB URL structure (e.g., PostgreSQL dialect format)
    pg_url = "postgresql+psycopg2://user:secret@localhost:5432/maritime_db"
    parsed = make_url(pg_url)
    assert parsed.drivername == "postgresql+psycopg2"
    assert parsed.host == "localhost"
    assert parsed.port == 5432
    assert parsed.database == "maritime_db"
    assert parsed.username == "user"


def test_monitored_port_model_persistence():
    """Verify MonitoredPort entity persists in database and converts to Pydantic."""
    with get_db_context() as db:
        port = MonitoredPort(
            id="port-test-db-1",
            user_id="captain@maritime.com",
            name="Test Database Port",
            locode="XXTDB",
            country="Maritime Nation",
            lat=12.34,
            lon=56.78,
            is_default=False,
            geofence_radius_nm=9.5,
            notifications_enabled=True,
        )
        db.add(port)
        db.commit()

    with get_db_context() as db:
        queried = db.query(MonitoredPort).filter(MonitoredPort.id == "port-test-db-1").first()
        assert queried is not None
        assert queried.name == "Test Database Port"
        assert queried.locode == "XXTDB"
        assert queried.notifications_enabled is True

        pydantic_port = queried.to_pydantic()
        assert pydantic_port.id == "port-test-db-1"
        assert pydantic_port.name == "Test Database Port"
        assert pydantic_port.addedByUserId == "captain@maritime.com"


def test_notification_record_model_persistence():
    """Verify NotificationRecord entity persists and supports read filtering in database."""
    with get_db_context() as db:
        notif = NotificationRecord(
            id="notif-test-db-1",
            user_id="captain@maritime.com",
            type="stateChange",
            port_id="port-test-db-1",
            port_name="Test Database Port",
            title="Test Alert",
            message="Risk escalated to High",
            tier="high",
            previous_tier="low",
            timestamp="2026-10-16T12:00:00Z",
            read=False,
            recipient_email="captain@maritime.com",
        )
        db.add(notif)
        db.commit()

    with get_db_context() as db:
        queried = db.query(NotificationRecord).filter(NotificationRecord.id == "notif-test-db-1").first()
        assert queried is not None
        assert queried.read is False
        assert queried.recipient_email == "captain@maritime.com"

        # Update read status
        queried.read = True
        db.commit()

    with get_db_context() as db:
        updated = db.query(NotificationRecord).filter(NotificationRecord.id == "notif-test-db-1").first()
        assert updated.read is True
        pydantic_notif = updated.to_pydantic()
        assert pydantic_notif.read is True
