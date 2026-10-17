"""Database engine and session management supporting SQLite and arbitrary SQL databases."""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import get_settings
from app.db.base import Base


def resolve_database_url(url: Optional[str] = None) -> str:
    """Resolve database connection URL from settings or parameter, handling relative SQLite paths."""
    if not url:
        settings = get_settings()
        url = settings.DATABASE_URL

    # Handle SQLite file path resolution when running from root or backend/
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        sqlite_path = url[len("sqlite:///"):]
        p = Path(sqlite_path)
        if not p.is_absolute():
            if p.exists() or p.parent.exists():
                resolved_path = str(p)
            elif p.parts and p.parts[0] == "backend":
                sub = Path(*p.parts[1:])
                if sub.exists() or sub.parent.exists():
                    resolved_path = str(sub)
                else:
                    resolved_path = str(p)
            else:
                resolved_path = str(p)

            # Ensure directory exists for sqlite database file
            Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{resolved_path}"

    return url


def create_app_engine(database_url: Optional[str] = None) -> Engine:
    """Create a database engine with dialect-specific options (e.g. check_same_thread for SQLite)."""
    url = resolve_database_url(database_url)
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(url, connect_args=connect_args)


engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(target_engine: Optional[Engine] = None) -> None:
    """Create all tables defined on Base if they do not exist and handle schema upgrades."""
    from sqlalchemy import inspect, text
    # Ensure models are imported so their metadata is registered on Base
    from app.db import models  # noqa: F401

    eng = target_engine or engine
    inspector = inspect(eng)
    if "monitored_ports" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("monitored_ports")]
        if "vessel_class" not in columns:
            with eng.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE monitored_ports_new (
                        id VARCHAR(64) NOT NULL PRIMARY KEY,
                        user_id VARCHAR(255) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        locode VARCHAR(10) NOT NULL,
                        country VARCHAR(100) NOT NULL,
                        lat FLOAT NOT NULL,
                        lon FLOAT NOT NULL,
                        is_default BOOLEAN NOT NULL,
                        geofence_radius_nm FLOAT NOT NULL,
                        notifications_enabled BOOLEAN NOT NULL,
                        vessel_class VARCHAR(50) NOT NULL DEFAULT 'neoPanamax',
                        created_at DATETIME NOT NULL,
                        CONSTRAINT uq_user_port_locode_vessel UNIQUE (user_id, locode, vessel_class)
                    )
                """))
                conn.execute(text("""
                    INSERT INTO monitored_ports_new (
                        id, user_id, name, locode, country, lat, lon, is_default,
                        geofence_radius_nm, notifications_enabled, vessel_class, created_at
                    )
                    SELECT
                        id, user_id, name, locode, country, lat, lon, is_default,
                        geofence_radius_nm, notifications_enabled, 'neoPanamax', created_at
                    FROM monitored_ports
                """))
                conn.execute(text("DROP TABLE monitored_ports"))
                conn.execute(text("ALTER TABLE monitored_ports_new RENAME TO monitored_ports"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_monitored_ports_user_id ON monitored_ports (user_id)"))

    if "notifications" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("notifications")]
        if "email_dispatched" not in columns:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN email_dispatched BOOLEAN NOT NULL DEFAULT 0"))

    Base.metadata.create_all(bind=eng)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context(target_sessionmaker=None) -> Generator[Session, None, None]:
    """Context manager for database sessions outside request scope (e.g. services, background jobs)."""
    sm = target_sessionmaker or SessionLocal
    db: Session = sm()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
