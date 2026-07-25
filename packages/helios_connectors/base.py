"""The connector contract every source implementation satisfies.

A connector is a pure translation layer: it turns a public source into
:class:`~helios_connectors.types.NormalizedRecord` objects and raw bytes. It
does not touch the database. Persistence is the pipeline's job
(:mod:`helios_connectors.pipeline`), which keeps connectors trivially testable
against recorded fixtures.

The seven-method contract mirrors the stages of ingestion::

    get_metadata -> health_check -> discover -> fetch -> parse -> normalize -> validate

Subclasses must implement ``get_metadata``, ``discover``, ``fetch``, ``parse``,
and ``normalize``. ``health_check`` and ``validate`` have workable defaults.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from helios_common.hashing import stable_json_hash
from helios_common.logging import get_logger
from helios_common.time import utcnow
from helios_connectors.http import PoliteHttpClient
from helios_connectors.types import (
    ConnectorMetadata,
    DateRange,
    DiscoveryResult,
    FetchResult,
    HealthCheckResult,
    NormalizationResult,
    NormalizedRecord,
    ParsedDocument,
    ParseResult,
    RawDocument,
    SourceItem,
    ValidationIssue,
    ValidationResult,
)

if TYPE_CHECKING:
    from helios_common.config import Settings

logger = get_logger(__name__)


class BaseConnector(ABC):
    """Abstract base for all Helios source connectors."""

    def __init__(
        self,
        *,
        http_client: PoliteHttpClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialise the connector.

        Args:
            http_client: Shared HTTP client. Fixture-backed connectors may omit
                this entirely and never construct one.
            settings: Configuration override.
        """
        self._http = http_client
        self._settings = settings

    @property
    def http(self) -> PoliteHttpClient:
        """The HTTP client, constructed lazily so offline connectors never need one."""
        if self._http is None:
            self._http = PoliteHttpClient(self._settings)
        return self._http

    # ------------------------------------------------------------ contract --

    @abstractmethod
    def get_metadata(self) -> ConnectorMetadata:
        """Return the static description of this connector and its source."""

    @abstractmethod
    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Enumerate the items available within a date window."""

    @abstractmethod
    def fetch(self, item: SourceItem) -> FetchResult:
        """Retrieve the bytes for one discovered item."""

    @abstractmethod
    def parse(self, document: RawDocument) -> ParseResult:
        """Turn raw bytes into structured, source-native records."""

    @abstractmethod
    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Map source-native records onto Helios domain concepts."""

    # ------------------------------------------------------------ defaults --

    def health_check(self) -> HealthCheckResult:
        """Probe source reachability with a cheap request.

        The default issues a GET against the source base URL. Connectors with a
        dedicated status endpoint should override this.

        Returns:
            Health status, never raising - an unreachable source is a result,
            not an exception.
        """
        metadata = self.get_metadata()
        started = utcnow()
        try:
            response = self.http.get(metadata.base_url)
        except Exception as exc:
            return HealthCheckResult(
                healthy=False,
                checked_at=started,
                message=f"{type(exc).__name__}: {exc}",
            )
        return HealthCheckResult(
            healthy=response.status_code < 400,
            checked_at=started,
            latency_ms=response.elapsed_ms,
            http_status=response.status_code,
        )

    def validate(self, record: NormalizedRecord) -> ValidationResult:
        """Check that a normalized record is safe to persist.

        The base implementation enforces universal invariants: an entity type, a
        source-native identifier, and - critically - that no record carrying an
        evidence kind lacks an observation date, since undated evidence cannot be
        placed on a timeline or excluded by a backtest cutoff.

        Args:
            record: The record to check.

        Returns:
            Validation outcome with per-field issues.
        """
        issues: list[ValidationIssue] = []

        if not record.entity_type:
            issues.append(ValidationIssue("entity_type", "Entity type is required"))
        if not record.source_native_id:
            issues.append(
                ValidationIssue("source_native_id", "Source-native identifier is required")
            )
        for item in record.evidence:
            if item.observed_at is None:
                issues.append(
                    ValidationIssue(
                        "observed_at",
                        f"Evidence {item.kind!r} has no observation date, so it could not be "
                        "placed on a timeline or correctly hidden by a backtest cutoff",
                    )
                )
            if not item.summary:
                issues.append(
                    ValidationIssue(item.kind, "Evidence must carry a human-readable summary")
                )
        for extracted in record.fields:
            if not 0.0 <= extracted.confidence <= 1.0:
                issues.append(
                    ValidationIssue(
                        extracted.name,
                        f"Confidence {extracted.confidence} outside [0, 1]",
                    )
                )

        return ValidationResult(valid=not any(i.severity == "error" for i in issues), issues=issues)

    # ------------------------------------------------------------- helpers --

    @staticmethod
    def field_signature(records: list[dict[str, object]]) -> str | None:
        """Hash the set of field names present across records.

        Comparing this hash between runs is how Helios notices that an agency
        renamed or removed a column. A silent rename would otherwise show up much
        later as unexplained nulls.

        Args:
            records: Source-native record dictionaries.

        Returns:
            A stable digest, or ``None`` when there are no records to inspect.
        """
        if not records:
            return None
        names: set[str] = set()
        for record in records:
            names.update(record.keys())
        return stable_json_hash(sorted(names))

    def close(self) -> None:
        """Release any resources held by the connector."""
        if self._http is not None:
            self._http.close()
            self._http = None


class FixtureBackedConnector(BaseConnector):
    """Base for connectors whose live source cannot be accessed responsibly.

    Several important Arizona sources - the ACC eDocket and most municipal
    agenda portals - are session-driven interfaces where automated access would
    require defeating technical controls. Rather than fabricate their data or
    quietly skip them, Helios ships the full parser and normalizer, tests them
    against fixtures captured from the documented schema, and records the access
    limitation in the registry so the gap is visible in the UI.

    Subclasses must set :attr:`fixture_dir` and implement ``parse`` and
    ``normalize`` exactly as a live connector would.
    """

    fixture_dir: str
    """Directory containing recorded payloads, relative to the fixtures root."""

    def fetch(self, item: SourceItem) -> FetchResult:
        """Read the recorded payload for an item instead of making a request."""
        from pathlib import Path

        path = Path(item.hints["fixture_path"])
        if not path.exists():
            return FetchResult(document=None, error=f"Fixture not found: {path}")
        payload = path.read_bytes()
        return FetchResult(
            document=RawDocument(
                item=item,
                payload=payload,
                mime_type=str(item.hints.get("mime_type", "application/json")),
                retrieved_at=utcnow(),
                http_status=None,
                headers={"x-helios-fixture": "true"},
            )
        )


__all__ = ["BaseConnector", "FixtureBackedConnector"]
