"""SQLAlchemy Declarative Base for database-agnostic models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy entities."""
    pass
