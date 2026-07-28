"""Orchestration of a full connector run.

The pipeline is the component that turns a connector's pure translation work
into durable, cited state. It owns three responsibilities connectors deliberately
do not have:

**Immutable versioning.** Fetched bytes are hashed and compared against the
versions already recorded for a document. Identical content produces no new
version, no new evidence, and no timeline change - which is what makes running
the same connector every night safe.

**Telemetry.** Every run writes a :class:`ConnectorRun` row with counts, HTTP
status distribution, retry totals, and schema-drift status, so a source that
quietly breaks becomes a visible metric rather than a gap nobody noticed.

**Failure isolation.** A single malformed record is recorded as an
:class:`IngestionFailure` and the run continues. One bad row must never cost the
other ten thousand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from helios_common.evidence_store import EvidenceStore
from helios_common.hashing import content_sha256
from helios_common.logging import bind_run_context, clear_run_context, get_logger
from helios_common.time import utcnow
from helios_connectors.loaders import (
    load_area_total,
    load_parcel,
    load_permit,
    load_substation,
    load_transmission_line,
)
from helios_connectors.types import DateRange, NormalizedRecord
from helios_domain.models import (
    ConnectorRun,
    DocumentVersion,
    IngestionFailure,
    Source,
    SourceConnector,
    SourceDocument,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from helios_connectors.base import BaseConnector
    from helios_connectors.types import ParsedDocument, RawDocument

logger = get_logger(__name__)


@dataclass(slots=True)
class RunSummary:
    """Aggregated outcome of one pipeline execution."""

    run_id: Any = None
    status: str = "success"
    items_discovered: int = 0
    items_fetched: int = 0
    items_parsed: int = 0
    items_normalized: int = 0
    items_rejected: int = 0
    items_filtered: int = 0
    items_unchanged: int = 0
    documents_created: int = 0
    versions_created: int = 0
    evidence_created: int = 0
    entities_upserted: int = 0
    redactions_applied: int = 0
    schema_drift_detected: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise for CLI output and API responses."""
        return {
            "run_id": str(self.run_id) if self.run_id else None,
            "status": self.status,
            "items_discovered": self.items_discovered,
            "items_fetched": self.items_fetched,
            "items_parsed": self.items_parsed,
            "items_normalized": self.items_normalized,
            "items_rejected": self.items_rejected,
            "items_filtered": self.items_filtered,
            "items_unchanged": self.items_unchanged,
            "documents_created": self.documents_created,
            "versions_created": self.versions_created,
            "evidence_created": self.evidence_created,
            "entities_upserted": self.entities_upserted,
            "redactions_applied": self.redactions_applied,
            "schema_drift_detected": self.schema_drift_detected,
            "errors": self.errors,
        }


class IngestionPipeline:
    """Executes a connector end to end and persists the results."""

    def __init__(
        self,
        session: Session,
        connector: BaseConnector,
        evidence_store: EvidenceStore,
        *,
        mode: str = "live",
        trigger: str = "manual",
    ) -> None:
        """Initialise the pipeline.

        Args:
            session: Open database session; the caller controls the transaction.
            connector: The connector to execute.
            evidence_store: Immutable store for raw payloads.
            mode: ``live`` or ``fixture``, recorded on the run.
            trigger: What initiated the run.
        """
        self.session = session
        self.connector = connector
        self.evidence_store = evidence_store
        self.mode = mode
        self.trigger = trigger
        self.metadata = connector.get_metadata()

    # ------------------------------------------------------------- run --

    def run(self, date_range: DateRange | None = None) -> RunSummary:
        """Execute discovery, fetch, parse, normalize, validate, and load.

        Args:
            date_range: Window to discover within; unbounded when omitted.

        Returns:
            A summary of what the run changed.
        """
        window = date_range or DateRange()
        source = self._require_source()
        connector_row = self._require_connector_row(source)
        run = self._start_run(connector_row)
        summary = RunSummary(run_id=run.id)

        bind_run_context(connector=self.metadata.slug, run_id=run.id, mode=self.mode)
        try:
            self._execute(run, source, summary, window)
        except Exception as exc:
            summary.status = "failed"
            summary.errors.append(f"{type(exc).__name__}: {exc}")
            logger.exception("pipeline.run_failed", connector=self.metadata.slug)
            self._record_failure(run, stage="run", category=type(exc).__name__, message=str(exc))
        finally:
            self._finish_run(run, connector_row, summary)
            clear_run_context()

        return summary

    def _execute(
        self,
        run: ConnectorRun,
        source: Source,
        summary: RunSummary,
        window: DateRange,
    ) -> None:
        """Run the pipeline stages for every discovered item."""
        discovery = self.connector.discover(window)
        summary.items_discovered = len(discovery.items)
        for message in discovery.errors:
            summary.errors.append(message)
            self._record_failure(run, stage="discover", category="discovery", message=message)

        for item in discovery.items:
            fetch_result = self.connector.fetch(item)
            if not fetch_result.ok or fetch_result.document is None:
                message = fetch_result.error or "fetch returned no document"
                summary.errors.append(message)
                self._record_failure(
                    run,
                    stage="fetch",
                    category="fetch_error",
                    message=message,
                    url=item.url,
                    native_id=item.source_native_id,
                )
                continue
            summary.items_fetched += 1

            raw = fetch_result.document
            document, version, is_new_version = self._store_document(run, source, raw)
            if is_new_version:
                summary.versions_created += 1
            else:
                summary.items_unchanged += 1

            parse_result = self.connector.parse(raw)
            if not parse_result.ok or parse_result.document is None:
                message = parse_result.error or "parse returned no document"
                summary.errors.append(message)
                self._record_failure(
                    run,
                    stage="parse",
                    category="parse_error",
                    message=message,
                    url=item.url,
                    native_id=item.source_native_id,
                )
                continue
            summary.items_parsed += 1

            parsed = parse_result.document
            self._check_schema_drift(run, parsed, summary)

            normalization = self.connector.normalize(parsed)
            summary.items_rejected += normalization.rejected
            summary.items_filtered += normalization.filtered

            for record in normalization.records:
                validation = self.connector.validate(record)
                if not validation.valid:
                    summary.items_rejected += 1
                    self._record_failure(
                        run,
                        stage="validate",
                        category="validation_error",
                        message="; ".join(validation.error_messages),
                        native_id=record.source_native_id,
                    )
                    continue

                summary.items_normalized += 1
                summary.redactions_applied += len(record.redactions_applied)
                try:
                    created_evidence = self._load(
                        record,
                        source=source,
                        document=document,
                        version=version,
                        create_evidence=is_new_version,
                    )
                except Exception as exc:
                    summary.items_rejected += 1
                    self.session.rollback()
                    self._record_failure(
                        run,
                        stage="persist",
                        category=type(exc).__name__,
                        message=str(exc),
                        native_id=record.source_native_id,
                    )
                    continue

                summary.entities_upserted += 1
                summary.evidence_created += created_evidence

        self.session.flush()

    # -------------------------------------------------------- documents --

    def _store_document(
        self, run: ConnectorRun, source: Source, raw: RawDocument
    ) -> tuple[SourceDocument, DocumentVersion, bool]:
        """Persist raw bytes immutably and attach a version to a document.

        Returns:
            The document, the current version, and whether the version is new.
        """
        digest = content_sha256(raw.payload)
        document = self._get_or_create_document(source, raw)

        existing = self.session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.content_sha256 == digest,
            )
        )
        document.last_seen_at = raw.retrieved_at
        if existing is not None:
            # Identical bytes: nothing new happened. This is the mechanism that
            # makes repeated ingestion produce no duplicate source records.
            logger.debug(
                "pipeline.content_unchanged",
                document=document.source_native_id,
                sha256=digest[:12],
            )
            return document, existing, False

        stored = self.evidence_store.put(
            source.slug,
            raw.payload,
            raw.mime_type,
            metadata={"source_native_id": raw.item.source_native_id},
        )

        previous = self.session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
        ).first()

        version = DocumentVersion(
            document_id=document.id,
            version_number=(previous.version_number + 1) if previous else 1,
            content_sha256=digest,
            content_length=len(raw.payload),
            mime_type=raw.mime_type,
            storage_key=stored.key,
            storage_backend=stored.backend,
            retrieved_at=raw.retrieved_at,
            source_url=raw.item.url,
            http_status=raw.http_status,
            http_headers=_safe_headers(raw.headers),
            etag=raw.etag,
            last_modified=raw.last_modified,
            connector_version=self.metadata.connector_version,
            parser_version=self.metadata.parser_version,
            run_id=run.id,
            supersedes_version_id=previous.id if previous else None,
        )
        self.session.add(version)
        self.session.flush()

        document.current_version_id = version.id
        document.version_count = version.version_number
        return document, version, True

    def _get_or_create_document(self, source: Source, raw: RawDocument) -> SourceDocument:
        """Find or create the logical document for a fetched item."""
        document = self.session.scalar(
            select(SourceDocument).where(
                SourceDocument.source_id == source.id,
                SourceDocument.source_native_id == raw.item.source_native_id,
            )
        )
        if document is None:
            document = SourceDocument(
                source_id=source.id,
                source_native_id=raw.item.source_native_id,
                title=raw.item.title,
                document_type=raw.item.document_type,
                source_url=raw.item.url,
                published_date=raw.item.published_date,
                effective_date=raw.item.effective_date,
                first_seen_at=raw.retrieved_at,
                last_seen_at=raw.retrieved_at,
            )
            self.session.add(document)
            self.session.flush()
        return document

    # ----------------------------------------------------------- loading --

    def _load(
        self,
        record: NormalizedRecord,
        *,
        source: Source,
        document: SourceDocument,
        version: DocumentVersion,
        create_evidence: bool,
    ) -> int:
        """Dispatch a normalized record to its loader.

        Returns:
            The number of evidence records created (0 or 1).
        """
        if record.entity_type == "parcel":
            _, evidence = load_parcel(
                self.session,
                record,
                source=source,
                document=document,
                version=version,
                create_evidence=create_evidence,
            )
            return len(evidence)
        if record.entity_type == "permit":
            _, evidence = load_permit(
                self.session,
                record,
                source=source,
                document=document,
                version=version,
                create_evidence=create_evidence,
            )
            return len(evidence)
        if record.entity_type == "area_total":
            load_area_total(self.session, record, source=source, version=version)
            return 0
        if record.entity_type == "substation":
            load_substation(self.session, record, source=source, document=document)
            return 0
        if record.entity_type == "transmission_line":
            load_transmission_line(self.session, record, source=source, document=document)
            return 0
        raise ValueError(f"No loader registered for entity type {record.entity_type!r}")

    # ------------------------------------------------------- bookkeeping --

    def _require_source(self) -> Source:
        """Fetch the registry-backed source row, failing loudly if absent."""
        source = self.session.scalar(select(Source).where(Source.slug == self.metadata.source_slug))
        if source is None:
            raise LookupError(
                f"Source {self.metadata.source_slug!r} is not registered. "
                "Run the registry sync before ingesting."
            )
        return source

    def _require_connector_row(self, source: Source) -> SourceConnector:
        """Fetch or create the connector row used to hang runs off."""
        connector_row = self.session.scalar(
            select(SourceConnector).where(SourceConnector.slug == self.metadata.slug)
        )
        if connector_row is None:
            connector_row = SourceConnector(
                slug=self.metadata.slug,
                source_id=source.id,
                entry_point=f"{type(self.connector).__module__}:{type(self.connector).__name__}",
                status=str(self.metadata.status),
            )
            self.session.add(connector_row)
            self.session.flush()
        return connector_row

    def _start_run(self, connector_row: SourceConnector) -> ConnectorRun:
        """Open a run record."""
        run = ConnectorRun(
            connector_id=connector_row.id,
            started_at=utcnow(),
            status="running",
            trigger=self.trigger,
            mode=self.mode,
            connector_version=self.metadata.connector_version,
            parser_version=self.metadata.parser_version,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def _finish_run(
        self, run: ConnectorRun, connector_row: SourceConnector, summary: RunSummary
    ) -> None:
        """Close the run record and update connector health."""
        run.finished_at = utcnow()
        run.status = summary.status
        run.items_discovered = summary.items_discovered
        run.items_fetched = summary.items_fetched
        run.items_parsed = summary.items_parsed
        run.items_normalized = summary.items_normalized
        run.items_rejected = summary.items_rejected
        run.items_filtered = summary.items_filtered
        run.items_unchanged = summary.items_unchanged
        run.documents_created = summary.documents_created
        run.versions_created = summary.versions_created
        run.evidence_created = summary.evidence_created
        run.schema_drift_detected = summary.schema_drift_detected
        run.message = "; ".join(summary.errors[:5]) if summary.errors else None

        http_stats = getattr(self.connector, "_http", None)
        if http_stats is not None:
            run.http_status_distribution = http_stats.stats.as_dict()
            run.retry_count = http_stats.stats.retries
            run.bytes_fetched = http_stats.stats.bytes_downloaded

        if summary.status == "success":
            connector_row.last_success_at = run.finished_at
        else:
            connector_row.last_failure_at = run.finished_at

        self.session.flush()
        logger.info("pipeline.run_finished", **summary.as_dict())

    def _check_schema_drift(
        self, run: ConnectorRun, parsed: ParsedDocument, summary: RunSummary
    ) -> None:
        """Compare the observed field set against the last recorded signature."""
        signature = parsed.field_signature
        if signature is None:
            return

        connector_row = self.session.get(SourceConnector, run.connector_id)
        if connector_row is None:
            return

        run.field_signature = signature
        previous = connector_row.last_field_signature
        if previous and previous != signature:
            summary.schema_drift_detected = True
            message = (
                f"Upstream field set changed for {self.metadata.slug}: "
                f"{previous[:12]} -> {signature[:12]}"
            )
            summary.errors.append(message)
            logger.warning("pipeline.schema_drift", connector=self.metadata.slug)
            self._record_failure(
                run, stage="parse", category="schema_drift", message=message, retryable=False
            )
        connector_row.last_field_signature = signature

    def _record_failure(
        self,
        run: ConnectorRun,
        *,
        stage: str,
        category: str,
        message: str,
        url: str | None = None,
        native_id: str | None = None,
        retryable: bool = True,
    ) -> None:
        """Write a dead-letter row so failures are countable, not just logged."""
        self.session.add(
            IngestionFailure(
                run_id=run.id,
                stage=stage,
                error_category=category,
                error_message=message[:4000],
                source_url=url,
                source_native_id=native_id,
                retryable=retryable,
            )
        )
        error_counts = dict(run.error_categories or {})
        error_counts[category] = error_counts.get(category, 0) + 1
        run.error_categories = error_counts


_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization"}


def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Drop credential-bearing headers before persisting response metadata."""
    return {k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS}


__all__ = ["IngestionPipeline", "RunSummary"]
