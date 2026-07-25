"""Engine and session management."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from helios_common.config import Settings, get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def create_engine_from_settings(settings: Settings | None = None) -> Engine:
    """Build a SQLAlchemy engine from configuration.

    Args:
        settings: Configuration to use; defaults to the process settings.

    Returns:
        A configured engine with connection pre-ping enabled.
    """
    cfg = settings or get_settings()
    engine = create_engine(
        cfg.sync_database_url,
        pool_size=cfg.database_pool_size,
        max_overflow=cfg.database_max_overflow,
        pool_pre_ping=True,
        echo=cfg.database_echo,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("SET TIME ZONE 'UTC'")
        finally:
            cursor.close()

    return engine


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine_from_settings()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, autoflush=False, future=True
        )
    return _session_factory


def reset_engine() -> None:
    """Dispose of the cached engine. Used by tests that switch databases."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope, committing on success and rolling back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def ensure_postgis(engine: Engine) -> None:
    """Create the extensions Helios relies on.

    Idempotent, and safe to call at migration time.

    Args:
        engine: Engine connected to the target database.
    """
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
