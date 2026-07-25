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

FIXTURES_ROOT = Path(__file__).parent / "fixtures"

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


def load_fixture_bytes(*parts: str) -> bytes:
    """Read a recorded fixture payload.

    Args:
        *parts: Path components below ``tests/fixtures``.

    Returns:
        The raw bytes exactly as captured from the source.
    """
    path = FIXTURES_ROOT.joinpath(*parts)
    if not path.exists():
        raise FileNotFoundError(f"Missing fixture: {path}")
    return path.read_bytes()
