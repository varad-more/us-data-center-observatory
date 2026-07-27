"""Shared pytest fixtures.

Two guarantees are established here for the whole suite:

* Live network access is disabled by default. A connector that tries to reach a
  real source during a unit test raises :class:`FetchBlockedError` rather than
  producing a result that depends on a county server being up.
* The evidence store and database point at disposable locations, so tests never
  touch a developer's working archive.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from helios_connectors.replay import FIXTURES_ROOT, load_fixture_bytes

TEST_DATABASE_URL = os.environ.get(
    "HELIOS_TEST_DATABASE_URL",
    "postgresql+psycopg://helios:helios@localhost:5432/helios_test",
)


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point every test at disposable configuration with live fetching disabled."""
    from helios_common.config import get_settings

    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.setenv("HELIOS_ALLOW_LIVE_FETCH", "false")
    # Code paths that build their own engine rather than taking the injected
    # session - the readiness probe, most obviously - must not reach a
    # developer's real database just because it is the ambient default.
    monkeypatch.setenv("HELIOS_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("HELIOS_EVIDENCE_BACKEND", "filesystem")
    monkeypatch.setenv("HELIOS_EVIDENCE_ROOT", str(tmp_path / "evidence-store"))
    monkeypatch.setenv("HELIOS_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("HELIOS_HTTP_BACKOFF_BASE_SECONDS", "0.001")
    monkeypatch.setenv("HELIOS_HTTP_BACKOFF_MAX_SECONDS", "0.01")
    monkeypatch.setenv("HELIOS_DEFAULT_RATE_LIMIT_PER_SECOND", "1000")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings():
    """Return the isolated test settings."""
    from helios_common.config import get_settings

    return get_settings()


@pytest.fixture
def evidence_store(settings):
    """A filesystem evidence store rooted in the test's temporary directory."""
    from helios_common.evidence_store import FilesystemEvidenceStore

    return FilesystemEvidenceStore(settings.evidence_root)


@pytest.fixture
def fixtures_root() -> Path:
    """Path to the recorded source fixtures."""
    return FIXTURES_ROOT


# ``load_fixture_bytes`` and ``FIXTURES_ROOT`` are re-exported from
# helios_connectors.replay so tests and the CLI read fixtures through one path.
__all__ = ["FIXTURES_ROOT", "load_fixture_bytes"]


# ---------------------------------------------------------------- database --
# Shared by integration and end-to-end tests. Unit/contract tests that do not
# request these fixtures never touch Postgres.


@pytest.fixture(scope="session")
def engine() -> Iterator[object]:
    """A session-scoped engine against the test database, with the schema created."""
    from sqlalchemy import create_engine, text

    import helios_domain.models  # noqa: F401
    from helios_domain.base import Base

    db_engine = create_engine(TEST_DATABASE_URL, future=True, poolclass=None)
    try:
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PostgreSQL/PostGIS not available at {TEST_DATABASE_URL}: {exc}")

    with db_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    Base.metadata.drop_all(db_engine)
    Base.metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture
def db_session(engine: object) -> Iterator[object]:
    """A transactional session rolled back at the end of each test."""
    from sqlalchemy.orm import sessionmaker

    connection = engine.connect()  # type: ignore[attr-defined]
    transaction = connection.begin()
    # autoflush=False mirrors the production session factory
    # (helios_domain.session). With autoflush left on, tests silently see
    # pending writes that the real application would not, which hid a bug where
    # every site reported zero evidence despite carrying a full evidence trail.
    factory = sessionmaker(bind=connection, expire_on_commit=False, autoflush=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def registered_sources(db_session: object) -> object:
    """A session with the declarative source registry synchronised."""
    from helios_connectors.sync import sync_registry

    sync_registry(db_session)  # type: ignore[arg-type]
    return db_session
