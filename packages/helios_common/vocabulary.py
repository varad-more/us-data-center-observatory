"""Controlled vocabularies that encode *epistemic status* throughout Helios.

Helios's central product rule is that an inferred value must never be rendered
the way a reported value is rendered. That rule is only enforceable if the
distinction is carried in the data model rather than reconstructed in the UI, so
these enums are persisted alongside almost every fact the system stores.
"""

from __future__ import annotations

from enum import StrEnum


class AssertionClass(StrEnum):
    """How a stored value came to be known.

    Ordered loosely from strongest to weakest epistemic standing. The API
    surfaces this verbatim so the frontend can pick a badge without re-deriving
    provenance semantics.
    """

    REPORTED = "reported"
    """Stated directly by an authoritative party in a primary source."""

    EXTRACTED = "extracted"
    """Read out of a source document by a parser, with a text span to prove it."""

    CALCULATED = "calculated"
    """Deterministically computed from other stored values (e.g. acreage from geometry)."""

    INFERRED = "inferred"
    """Concluded from indirect signals; may be wrong even when every input is correct."""

    PREDICTED = "predicted"
    """Model output about a future or unobserved state."""

    UNKNOWN = "unknown"
    """Explicitly not established. Distinct from null, which means 'not yet looked at'."""

    @property
    def is_verifiable(self) -> bool:
        """Whether a user can trace this value to a specific source span."""
        return self in {AssertionClass.REPORTED, AssertionClass.EXTRACTED}


class ExtractionMethod(StrEnum):
    """The mechanism that produced a fact, recorded for reproducibility."""

    STRUCTURED_FEED = "structured_feed"
    """Read from a typed field in an API or dataset; no interpretation applied."""

    REGEX = "regex"
    PATTERN_RULE = "pattern_rule"
    TABLE_PARSE = "table_parse"
    GEOMETRY_OPERATION = "geometry_operation"
    RULE_ENGINE = "rule_engine"
    STATISTICAL_MODEL = "statistical_model"
    HUMAN_ENTRY = "human_entry"
    MANUAL_CURATION = "manual_curation"


class EvidencePolarity(StrEnum):
    """Whether an evidence record argues for or against a hypothesis."""

    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    NEUTRAL = "neutral"


class HumanReviewStatus(StrEnum):
    """Review state for machine-generated assertions."""

    NOT_REVIEWED = "not_reviewed"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class ConfidenceBand(StrEnum):
    """Coarse buckets used for display so that precise-looking percentages do not overclaim."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceBand:
        """Bucket a 0-100 confidence score.

        Args:
            score: Confidence on a 0-100 scale.

        Returns:
            The band the score falls into.
        """
        if score < 20:
            return cls.VERY_LOW
        if score < 40:
            return cls.LOW
        if score < 60:
            return cls.MODERATE
        if score < 80:
            return cls.HIGH
        return cls.VERY_HIGH


class SourceCategory(StrEnum):
    """Taxonomy used by the source registry."""

    LAND_AND_PROPERTY = "land_and_property"
    MUNICIPAL_PLANNING = "municipal_planning"
    UTILITY_AND_REGULATORY = "utility_and_regulatory"
    ENVIRONMENTAL = "environmental"
    WATER = "water"
    CORPORATE = "corporate"
    CONNECTIVITY = "connectivity"
    REMOTE_SENSING = "remote_sensing"
    INFRASTRUCTURE_REFERENCE = "infrastructure_reference"
    VALIDATION = "validation"
    NEWS_AND_CLAIMS = "news_and_claims"


class AccessMethod(StrEnum):
    """How a source is reached, which determines connector shape and legal posture."""

    REST_JSON = "rest_json"
    ARCGIS_REST = "arcgis_rest"
    SOCRATA = "socrata"
    OVERPASS = "overpass"
    BULK_DOWNLOAD = "bulk_download"
    HTML_PAGE = "html_page"
    RSS = "rss"
    MANUAL_UPLOAD = "manual_upload"
    """Records obtained by a human (e.g. a records request) and loaded deliberately."""


class ConnectorStatus(StrEnum):
    """Lifecycle state of a connector implementation."""

    PLANNED = "planned"
    """Registry entry exists; no code yet."""

    FIXTURE_ONLY = "fixture_only"
    """Interface and parser implemented and tested, but live access is blocked."""

    IMPLEMENTED = "implemented"
    """Runs against the live source."""

    DEGRADED = "degraded"
    DISABLED = "disabled"


__all__ = [
    "AccessMethod",
    "AssertionClass",
    "ConfidenceBand",
    "ConnectorStatus",
    "EvidencePolarity",
    "ExtractionMethod",
    "HumanReviewStatus",
    "SourceCategory",
]
