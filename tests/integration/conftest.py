"""Database fixtures for integration tests.

Each test runs inside a transaction that is rolled back afterwards, so tests
share one migrated database without leaking state into each other.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from helios_domain.base import Base
from tests.conftest import TEST_DATABASE_URL

# Importing models registers every table on the shared metadata.
import helios_domain.models  # noqa: F401  isort: skip


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """A session-scoped engine against the test database, with the schema created."""
    engine = create_engine(TEST_DATABASE_URL, future=True, poolclass=None)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PostgreSQL/PostGIS not available at {TEST_DATABASE_URL}: {exc}")

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A transactional session rolled back at the end of each test."""
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def registered_sources(db_session: Session) -> Session:
    """A session with the declarative source registry synchronised."""
    from helios_connectors.sync import sync_registry

    sync_registry(db_session)
    return db_session
