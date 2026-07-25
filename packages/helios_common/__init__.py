"""Shared primitives for Project Helios.

This package holds cross-cutting concerns that every other Helios package is
allowed to depend on: configuration, logging, hashing, time handling, and the
vocabulary enums that express *how certain* the system is about a fact.

Nothing in here may import from :mod:`helios_domain` or any application layer.
"""

from helios_common.config import Settings, get_settings
from helios_common.hashing import content_sha256, stable_json_hash
from helios_common.logging import configure_logging, get_logger
from helios_common.time import parse_flexible_date, utcnow
from helios_common.vocabulary import (
    AssertionClass,
    ConfidenceBand,
    EvidencePolarity,
    ExtractionMethod,
    HumanReviewStatus,
)

__all__ = [
    "AssertionClass",
    "ConfidenceBand",
    "EvidencePolarity",
    "ExtractionMethod",
    "HumanReviewStatus",
    "Settings",
    "configure_logging",
    "content_sha256",
    "get_logger",
    "get_settings",
    "parse_flexible_date",
    "stable_json_hash",
    "utcnow",
]
