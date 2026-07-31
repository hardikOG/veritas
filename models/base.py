"""Shared SQLAlchemy declarative base for all Veritas ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by all Veritas ORM models."""
