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


def test_external_weather_cache_persistence_and_freshness():
    """Verify ExternalWeatherCache entity persists, converts to Pydantic, and tracks freshness."""
    from datetime import datetime, timezone, timedelta
    from app.db.models import ExternalWeatherCache

    now = datetime.now(timezone.utc)
    with get_db_context() as db:
        record = ExternalWeatherCache(
            id="51.92:4.48",
            lat=51.92,
            lon=4.48,
            port_id="port-rtm-01",
            wind_speed_knots=24.5,
            gust_speed_knots=31.2,
            wave_height_m=2.1,
            swell_period_sec=6.5,
            visibility_nm=9.0,
            source="open-meteo",
            fetched_at=now,
        )
        db.add(record)
        db.commit()

    with get_db_context() as db:
        queried = db.query(ExternalWeatherCache).filter(ExternalWeatherCache.id == "51.92:4.48").first()
        assert queried is not None
        assert queried.wind_speed_knots == 24.5
        assert queried.source == "open-meteo"
        assert queried.is_fresh(1800.0) is True

        # Test stale check
        queried.fetched_at = now - timedelta(minutes=45)
        db.commit()

    with get_db_context() as db:
        stale_record = db.query(ExternalWeatherCache).filter(ExternalWeatherCache.id == "51.92:4.48").first()
        assert stale_record.is_fresh(1800.0) is False
        pydantic_weather = stale_record.to_pydantic()
        assert pydantic_weather.windSpeedKnots == 24.5
        assert pydantic_weather.waveHeightM == 2.1


def test_external_ais_traffic_cache_persistence_and_freshness():
    """Verify ExternalAISTrafficCache entity persists, tracks freshness, and converts to Pydantic."""
    from datetime import datetime, timezone, timedelta
    from app.db.models import ExternalAISTrafficCache

    now = datetime.now(timezone.utc)
    with get_db_context() as db:
        record = ExternalAISTrafficCache(
            id="port-rtm-01:panamax",
            port_id="port-rtm-01",
            locode="NLRTM",
            vessel_class="panamax",
            anchorage_queue_count=14,
            avg_waiting_time_hours=19.5,
            berth_occupancy_pct=78.0,
            rolling_30d_avg_queue=11.0,
            rolling_30d_avg_wait_hours=18.0,
            berth_turnaround_hours=26.0,
            berth_to_anchorage_wait_ratio=0.55,
            dwell_time_anomaly_score=42.0,
            rolling_30d_avg_turnaround=25.0,
            under_keel_clearance_m=2.2,
            channel_depth_m=15.5,
            air_draft_clearance_m=7.0,
            pilotage_available=True,
            tide_height_m=1.8,
            source="aisstream",
            fetched_at=now,
        )
        db.add(record)
        db.commit()

    with get_db_context() as db:
        queried = db.query(ExternalAISTrafficCache).filter(ExternalAISTrafficCache.id == "port-rtm-01:panamax").first()
        assert queried is not None
        assert queried.anchorage_queue_count == 14
        assert queried.is_fresh(1800.0) is True

        cong, term, nav = queried.to_pydantic()
        assert cong.anchorageQueueCount == 14
        assert term.berthTurnaroundHours == 26.0
        assert nav.channelDepthM == 15.5

        # Test stale check
        queried.fetched_at = now - timedelta(minutes=35)
        db.commit()

    with get_db_context() as db:
        stale_record = db.query(ExternalAISTrafficCache).filter(ExternalAISTrafficCache.id == "port-rtm-01:panamax").first()
        assert stale_record.is_fresh(1800.0) is False
