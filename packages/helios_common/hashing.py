"""Content hashing used for document identity and idempotent ingestion.

Helios decides whether a fetched document is *new* purely by comparing the
SHA-256 of its bytes against the versions already stored. That makes repeated
connector runs safe: re-fetching unchanged content adds no rows.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def content_sha256(payload: bytes) -> str:
    """Return the hex SHA-256 of a byte payload."""
    return hashlib.sha256(payload).hexdigest()


def stable_json_hash(value: Any) -> str:
    """Hash a JSON-serialisable value independent of key ordering.

    Used to detect schema drift: a connector hashes the *field names* it saw and
    compares against the last run, so a silently renamed upstream column raises
    an alert instead of quietly producing nulls.

    Args:
        value: Any JSON-serialisable structure.

    Returns:
        Hex SHA-256 digest of the canonical encoding.
    """
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def short_hash(value: str, length: int = 12) -> str:
    """Return a truncated digest suitable for human-facing identifiers."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
