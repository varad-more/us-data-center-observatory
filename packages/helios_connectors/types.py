"""Data-transfer objects exchanged between connector pipeline stages.

Each stage of the connector contract consumes the previous stage's output, which
keeps connectors testable one step at a time: a parser can be exercised against
a recorded :class:`RawDocument` with no network, and a normalizer against a
:class:`ParsedDocument` with no parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from helios_common.vocabulary import (
    AccessMethod,
    AssertionClass,
    ConnectorStatus,
    ExtractionMethod,
    SourceCategory,
)


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive window used to scope discovery."""

    start: date | None = None
    end: date | None = None

    def contains(self, value: date | None) -> bool:
        """Return whether a date falls inside the window.

        A ``None`` value is treated as in-range, because many sources omit dates
        and excluding them would silently drop records.
        """
        if value is None:
            return True
        if self.start and value < self.start:
            return False
        return not (self.end and value > self.end)


@dataclass(frozen=True, slots=True)
class ConnectorMetadata:
    """Static description of a connector and the source it reads."""

    slug: str
    source_slug: str
    name: str
    agency: str
    jurisdiction: str
    category: SourceCategory
    access_method: AccessMethod
    base_url: str
    connector_version: str
    parser_version: str
    status: ConnectorStatus
    update_frequency: str | None = None
    rate_limit_per_second: float | None = None
    requires_authentication: bool = False
    license_name: str | None = None
    license_url: str | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    robots_policy_status: str | None = None
    contains_personal_data: bool = False
    geographic_coverage: str | None = None
    historical_coverage: str | None = None
    known_schema_issues: str | None = None
    access_limitation: str | None = None
    """Populated for fixture-only connectors, explaining what blocks live access."""

    reliability_score: float | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    """Outcome of a lightweight source-reachability probe."""

    healthy: bool
    checked_at: datetime
    latency_ms: float | None = None
    http_status: int | None = None
    message: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceItem:
    """A discovered unit of work: one document the connector intends to fetch."""

    source_native_id: str
    url: str
    title: str | None = None
    document_type: str | None = None
    published_date: date | None = None
    effective_date: date | None = None
    hints: dict[str, Any] = field(default_factory=dict)
    """Connector-private context (query parameters, pagination offsets)."""


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Items found for a date range, plus any non-fatal problems."""

    items: list[SourceItem]
    truncated: bool = False
    """True when a source paging limit stopped enumeration early."""

    errors: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawDocument:
    """Bytes as received from a source, with the HTTP context that produced them."""

    item: SourceItem
    payload: bytes
    mime_type: str
    retrieved_at: datetime
    http_status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    etag: str | None = None
    last_modified: str | None = None
    from_cache: bool = False
    """True when the server answered 304 Not Modified and content was reused."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Result of fetching one item."""

    document: RawDocument | None
    unchanged: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether a payload is available."""
        return self.document is not None and self.error is None


@dataclass(frozen=True, slots=True)
class ExtractedField:
    """A single extracted value with the provenance needed to defend it.

    ``raw_text`` and ``raw_unit`` are retained next to the normalized value so a
    reviewer can see exactly what the source said, not just what Helios made of
    it.
    """

    name: str
    value: Any
    raw_text: str | None = None
    raw_unit: str | None = None
    normalized_unit: str | None = None
    assertion_class: AssertionClass = AssertionClass.EXTRACTED
    extraction_method: ExtractionMethod = ExtractionMethod.STRUCTURED_FEED
    confidence: float = 0.9
    locator: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    snippet: str | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialise for storage in ``evidence_records.normalized_values``."""
        return {
            "name": self.name,
            "value": self.value,
            "raw_text": self.raw_text,
            "raw_unit": self.raw_unit,
            "normalized_unit": self.normalized_unit,
            "assertion_class": str(self.assertion_class),
            "extraction_method": str(self.extraction_method),
            "confidence": self.confidence,
            "locator": self.locator,
        }


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Structured content read out of a raw document."""

    raw: RawDocument
    document_type: str
    text: str | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    """One dict per logical row, still in source-native field names."""

    fields: list[ExtractedField] = field(default_factory=list)
    tables: list[list[dict[str, Any]]] = field(default_factory=list)
    field_signature: str | None = None
    """Hash of observed field names, compared across runs to detect schema drift."""

    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Result of parsing one raw document."""

    document: ParsedDocument | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether parsing produced a document."""
        return self.document is not None and self.error is None


@dataclass(slots=True)
class NormalizedRecord:
    """A source record mapped onto Helios domain concepts.

    ``entity_type`` selects which persistence path the loader takes, and
    ``payload`` carries already-normalised field values keyed by domain
    attribute name.
    """

    entity_type: str
    source_native_id: str
    payload: dict[str, Any]
    fields: list[ExtractedField] = field(default_factory=list)
    evidence_kind: str | None = None
    evidence_summary: str | None = None
    observed_at: date | None = None
    geometry_wkt: str | None = None
    warnings: list[str] = field(default_factory=list)
    redactions_applied: list[str] = field(default_factory=list)
    """Names of fields suppressed by PII policy, recorded for transparency."""


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Result of normalizing one parsed document."""

    records: list[NormalizedRecord]
    rejected: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation problem found in a normalized record."""

    field_name: str
    message: str
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of validating one normalized record."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_messages(self) -> list[str]:
        """Messages for issues at error severity."""
        return [i.message for i in self.issues if i.severity == "error"]


__all__ = [
    "ConnectorMetadata",
    "DateRange",
    "DiscoveryResult",
    "ExtractedField",
    "FetchResult",
    "HealthCheckResult",
    "NormalizationResult",
    "NormalizedRecord",
    "ParseResult",
    "ParsedDocument",
    "RawDocument",
    "SourceItem",
    "ValidationIssue",
    "ValidationResult",
]
