"""Unit tests for Settings — specifically the database_url dialect normalization
that a real Render deploy attempt surfaced was missing (see BUGJOURNAL.md)."""

from core.config import Settings


def test_bare_postgresql_scheme_is_forced_to_psycopg() -> None:
    settings = Settings(database_url="postgresql://user:pass@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://user:pass@host:5432/db"


def test_short_postgres_scheme_is_forced_to_psycopg() -> None:
    """Heroku/Render-style short scheme -- another common managed-Postgres shape."""
    settings = Settings(database_url="postgres://user:pass@host:5432/db")
    assert settings.database_url == "postgresql+psycopg://user:pass@host:5432/db"


def test_already_correct_url_is_left_unchanged() -> None:
    url = "postgresql+psycopg://user:pass@host:5432/db"
    settings = Settings(database_url=url)
    assert settings.database_url == url


def test_unrecognized_scheme_passes_through_unchanged_not_raised() -> None:
    url = "sqlite:///somewhere.db"
    settings = Settings(database_url=url)
    assert settings.database_url == url
