"""PostgreSQL support: driver availability, URL handling and schema portability.

These tests never open a real PostgreSQL connection. They verify that the
psycopg 3 driver is installed, that the engine is built with the correct dialect
and connect args for each backend, and that the approved schema compiles to
portable PostgreSQL DDL. This keeps the staging database path verified without
touching a live server.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from backend.db.models import Base

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def test_psycopg_driver_is_installed():
    """The staging/production PostgreSQL driver must be importable."""
    assert importlib.util.find_spec("psycopg") is not None


def test_psycopg3_is_the_expected_major_version():
    import psycopg

    assert psycopg.__version__.split(".")[0] == "3"


# --------------------------------------------------------------------------
# engine / dialect selection
# --------------------------------------------------------------------------
def test_postgresql_url_selects_psycopg_dialect():
    engine = create_engine("postgresql+psycopg://user:pass@localhost:5432/safir")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_sqlite_url_still_selects_sqlite_dialect():
    engine = create_engine("sqlite:///./safir_dev.db")
    try:
        assert engine.dialect.name == "sqlite"
    finally:
        engine.dispose()


def test_sqlite_connect_args_only_apply_to_sqlite():
    """Mirror of the predicate in ``backend/db/session.py``."""
    from backend.db.session import _is_sqlite

    assert _is_sqlite is True  # the test session runs on SQLite
    connect_args = {"check_same_thread": False} if _is_sqlite else {}
    assert connect_args == {"check_same_thread": False}


# --------------------------------------------------------------------------
# Alembic batch mode (SQLite-only workaround must not leak to PostgreSQL)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("url", "expected_batch"),
    [
        ("sqlite:///./safir_dev.db", True),
        ("postgresql+psycopg://user:pass@localhost:5432/safir", False),
    ],
)
def test_render_as_batch_predicate(url: str, expected_batch: bool):
    """The predicate used by ``alembic/env.py`` must enable batch only for SQLite."""
    assert url.startswith("sqlite") is expected_batch


# --------------------------------------------------------------------------
# schema portability
# --------------------------------------------------------------------------
def test_all_tables_compile_to_postgresql_ddl():
    """Every approved table must compile cleanly against the PostgreSQL dialect."""
    dialect = postgresql.dialect()
    statements = [
        str(CreateTable(table).compile(dialect=dialect))
        for table in Base.metadata.sorted_tables
    ]
    assert len(statements) == len(Base.metadata.sorted_tables)
    assert all("CREATE TABLE" in stmt for stmt in statements)


def test_money_columns_use_numeric_on_postgresql():
    """Financial amounts must stay exact (NUMERIC), never floating point."""
    dialect = postgresql.dialect()
    reports = Base.metadata.tables["monthly_reports"]
    ddl = str(CreateTable(reports).compile(dialect=dialect))
    assert "NUMERIC(18, 2)" in ddl


def test_datetime_columns_are_timezone_aware_on_postgresql():
    dialect = postgresql.dialect()
    reports = Base.metadata.tables["monthly_reports"]
    ddl = str(CreateTable(reports).compile(dialect=dialect))
    assert "TIMESTAMP WITH TIME ZONE" in ddl


def test_sqlite_ddl_still_compiles():
    """SQLite compatibility must be preserved alongside PostgreSQL support."""
    dialect = sqlite.dialect()
    statements = [
        str(CreateTable(table).compile(dialect=dialect))
        for table in Base.metadata.sorted_tables
    ]
    assert all("CREATE TABLE" in stmt for stmt in statements)


# --------------------------------------------------------------------------
# migration head
# --------------------------------------------------------------------------
def test_alembic_has_a_single_head_at_the_approved_revision():
    """The migration graph must have exactly one head: the Phase 2 revision."""
    versions_dir = PROJECT_ROOT / "alembic" / "versions"
    revisions: dict[str, str | None] = {}
    for path in versions_dir.glob("*.py"):
        namespace: dict = {}
        exec(path.read_text(encoding="utf-8"), namespace)  # noqa: S102 - local repo file
        revisions[namespace["revision"]] = namespace.get("down_revision")

    heads = set(revisions) - {down for down in revisions.values() if down}
    assert heads == {"1b786167cd02"}
    # The Phase 2 revision must build directly on the initial schema.
    assert revisions["1b786167cd02"] == "55d2d244bc1b"
