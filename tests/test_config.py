"""Unit tests for core/config.py — the database URL is assembled three
different ways depending on which env vars are set."""

from __future__ import annotations

from core.config import Settings


def _settings(**kw) -> Settings:
    # _env_file=None so a developer's local .env can't influence the test.
    return Settings(_env_file=None, **kw)


def test_explicit_database_url_wins():
    s = _settings(database_url="postgresql+psycopg://u:p@host:5432/db")
    assert s.sqlalchemy_database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_cloud_sql_connection_name_builds_unix_socket_url():
    s = _settings(
        cloud_sql_connection_name="proj:us-central1:inst",
        db_user="app",
        db_password="secret",
        db_name="kb",
    )
    url = s.sqlalchemy_database_url
    assert url == "postgresql+psycopg://app:secret@/kb?host=/cloudsql/proj:us-central1:inst"


def test_local_fallback_when_nothing_configured():
    s = _settings(db_user="app", db_password="pw", db_name="kb")
    assert s.sqlalchemy_database_url == "postgresql+psycopg://app:pw@localhost:5432/kb"


def test_collection_name_default_matches_uac_project():
    # Sharing this default lets the server point at the sibling project's DB.
    assert _settings().vector_collection_name == "uc_davis_ai"
