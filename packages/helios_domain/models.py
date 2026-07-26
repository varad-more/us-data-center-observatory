"""Relational models for the Helios Phase 1 schema.

Layered roughly in dependency order:

1. **Source registry** - what public sources exist and how healthy they are.
2. **Evidence spine** - append-only documents, versions, and extracted facts.
3. **Actors** - organizations and their time-bounded relationships.
4. **Physical world** - parcels, sites, and power infrastructure, all in PostGIS.
5. **Regulatory** - permits.
6. **Analysis** - stage history, scored predictions, estimates, human review.

Two invariants hold everywhere and are enforced with database constraints
rather than convention:

* Nothing in the evidence spine is ever mutated in place. A changed document
  produces a new :class:`DocumentVersion`.
* Every analytical output points back at the evidence that produced it, and
  carries the model version that produced it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column, relationship

from helios_domain.base import (
    Base,
    EffectiveDatingMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

# Geometry aliases keep the SRID declaration in one place. 4326 is used for
# storage and API output; metric work is done by casting to geography or
# projecting to 26912 (NAD83 / UTM 12N, appropriate for Arizona) at query time.
_Polygon = Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False)
_Point = Geometry(geometry_type="POINT", srid=4326, spatial_index=False)
_Line = Geometry(geometry_type="MULTILINESTRING", srid=4326, spatial_index=False)


# ============================================================ source registry ==


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A public data source Helios is permitted to read.

    The registry exists *before* any connector so that legal posture, licensing,
    and rate limits are recorded decisions rather than properties accidentally
    encoded in scraper code.
    """

    __tablename__ = "sources"

    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    agency: Mapped[str] = mapped_column(String(300), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    access_method: Mapped[str] = mapped_column(String(40), nullable=False)

    update_frequency: Mapped[str | None] = mapped_column(String(80))
    requires_authentication: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authentication_notes: Mapped[str | None] = mapped_column(Text)
    rate_limit_per_second: Mapped[float | None] = mapped_column(Float)
    rate_limit_notes: Mapped[str | None] = mapped_column(Text)

    license_name: Mapped[str | None] = mapped_column(String(200))
    license_url: Mapped[str | None] = mapped_column(Text)
    licensing_notes: Mapped[str | None] = mapped_column(Text)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attribution_text: Mapped[str | None] = mapped_column(Text)

    robots_policy_status: Mapped[str | None] = mapped_column(String(60))
    """Result of checking robots.txt: ``allowed``, ``disallowed``, ``not_applicable``."""
    robots_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_of_service_url: Mapped[str | None] = mapped_column(Text)

    geographic_coverage: Mapped[str | None] = mapped_column(Text)
    historical_coverage: Mapped[str | None] = mapped_column(Text)
    """Plain-language statement of how far back the source goes; drives backtest feasibility."""

    contains_personal_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """Triggers the PII redaction path during normalization."""

    reliability_score: Mapped[float | None] = mapped_column(Float)
    known_schema_issues: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    connectors: Mapped[list[SourceConnector]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    documents: Mapped[list[SourceDocument]] = relationship(back_populates="source")

    __table_args__ = (
        CheckConstraint(
            "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)",
            name="reliability_score_range",
        ),
        Index("ix_sources_jurisdiction_category", "jurisdiction", "category"),
    )


class SourceConnector(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete connector implementation bound to a source."""

    __tablename__ = "source_connectors"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    entry_point: Mapped[str] = mapped_column(String(300), nullable=False)
    """Dotted import path, e.g. ``helios_connectors.maricopa_assessor:AssessorConnector``."""

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="planned")
    connector_version: Mapped[str] = mapped_column(String(30), nullable=False, default="0.1.0")
    parser_version: Mapped[str] = mapped_column(String(30), nullable=False, default="0.1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(80))

    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_field_signature: Mapped[str | None] = mapped_column(String(64))
    """Hash of the upstream field names last observed; a change means schema drift."""

    access_limitation: Mapped[str | None] = mapped_column(Text)
    """Why a connector is fixture-only, recorded honestly rather than hidden."""

    source: Mapped[Source] = relationship(back_populates="connectors")
    runs: Mapped[list[ConnectorRun]] = relationship(
        back_populates="connector", cascade="all, delete-orphan"
    )


class ConnectorRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Telemetry for one execution of a connector."""

    __tablename__ = "connector_runs"

    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")

    trigger: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="live")
    """``live`` or ``fixture``; keeps replayed runs distinguishable from real ones."""

    items_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_normalized: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Records that should have loaded but did not. Non-zero means investigate."""

    items_filtered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    """Records deliberately excluded by connector scope. Expected to be large and
    healthy; kept apart from ``items_rejected`` so alerting stays meaningful."""

    items_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    versions_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_fetched: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    http_status_distribution: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    error_categories: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    schema_drift_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    field_signature: Mapped[str | None] = mapped_column(String(64))

    connector_version: Mapped[str | None] = mapped_column(String(30))
    parser_version: Mapped[str | None] = mapped_column(String(30))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)

    connector: Mapped[SourceConnector] = relationship(back_populates="runs")
    failures: Mapped[list[IngestionFailure]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="run_finishes_after_start"
        ),
        Index("ix_connector_runs_connector_started", "connector_id", "started_at"),
    )

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock run duration, or ``None`` if still running."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


class IngestionFailure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dead-letter record for an item that could not be ingested.

    Failures are first-class rows rather than log lines so that a source silently
    breaking shows up as a countable metric and can be replayed after a fix.
    """

    __tablename__ = "ingestion_failures"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connector_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    """Pipeline stage that failed: discover, fetch, parse, normalize, validate, persist."""

    error_category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_native_id: Mapped[str | None] = mapped_column(String(200))
    payload_excerpt: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[ConnectorRun] = relationship(back_populates="failures")


# ============================================================= evidence spine ==


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A logical document from a source, identified by its source-native key.

    The row itself is stable; its *content* lives in one or more
    :class:`DocumentVersion` rows. This split is what lets Helios answer "what
    did this permit record say in March?" after the agency edits it in July.
    """

    __tablename__ = "source_documents"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_native_id: Mapped[str] = mapped_column(String(300), nullable=False)
    """The identifier the *agency* uses. Preserved verbatim for citation."""

    title: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(String(80), index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)

    published_date: Mapped[date | None] = mapped_column(Date, index=True)
    """Document time - when the source published it. Used by backtest cutoffs."""

    effective_date: Mapped[date | None] = mapped_column(Date, index=True)
    """Valid time - when the described fact took effect, if stated."""

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    version_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """True for fixture-derived records. Surfaced in the API so demo data is never
    mistaken for a live public record."""

    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    """Source-specific fields that resist normalization. Deliberately narrow."""

    source: Mapped[Source] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
        foreign_keys="DocumentVersion.document_id",
    )
    evidence_records: Mapped[list[EvidenceRecord]] = relationship(back_populates="document")

    __table_args__ = (
        UniqueConstraint("source_id", "source_native_id", name="source_native_id_unique"),
        Index("ix_source_documents_published", "source_id", "published_date"),
    )


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An immutable snapshot of document content.

    Rows here are never updated. The raw bytes live in the evidence store under
    a key derived from ``content_sha256``, so the database holds the metadata and
    object storage holds the payload.
    """

    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_length: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False, default="filesystem")

    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Transaction time - when Helios fetched these exact bytes."""

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    http_headers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    etag: Mapped[str | None] = mapped_column(String(300))
    last_modified: Mapped[str | None] = mapped_column(String(120))

    connector_version: Mapped[str | None] = mapped_column(String(30))
    parser_version: Mapped[str | None] = mapped_column(String(30))
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connector_runs.id", ondelete="SET NULL")
    )
    supersedes_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL")
    )

    document: Mapped[SourceDocument] = relationship(
        back_populates="versions", foreign_keys=[document_id]
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="document_version_number_unique"),
        UniqueConstraint("document_id", "content_sha256", name="document_content_unique"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("content_length >= 0", name="content_length_non_negative"),
        Index("ix_document_versions_retrieved", "document_id", "retrieved_at"),
    )


class EvidenceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One atomic, cited fact extracted from a document version.

    This is the unit the whole product is built on. Every scoring contribution,
    stage transition, and timeline entry points at one of these, and every one of
    these points at a byte range in an immutable document version.
    """

    __tablename__ = "evidence_records"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), index=True
    )
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="SET NULL"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )

    evidence_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    """Verbatim text from the source. The 'show me where you read that' field."""

    snippet_start_offset: Mapped[int | None] = mapped_column(Integer)
    snippet_end_offset: Mapped[int | None] = mapped_column(Integer)
    snippet_locator: Mapped[str | None] = mapped_column(String(200))
    """Structural pointer: page number, JSON path, or table cell reference."""

    observed_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    """The date this evidence pertains to - the timeline axis."""

    assertion_class: Mapped[str] = mapped_column(String(20), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False, default="supporting")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    parser_version: Mapped[str] = mapped_column(String(30), nullable=False, default="0.1.0")
    human_review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_reviewed"
    )

    normalized_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    """Unit-normalized extractions, each retaining its original text and unit."""

    document: Mapped[SourceDocument] = relationship(back_populates="evidence_records")
    site: Mapped[Site | None] = relationship(back_populates="evidence_records")

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(
            "snippet_end_offset IS NULL OR snippet_start_offset IS NULL "
            "OR snippet_end_offset >= snippet_start_offset",
            name="snippet_offsets_ordered",
        ),
        Index("ix_evidence_site_observed", "site_id", "observed_at"),
        Index("ix_evidence_kind_observed", "evidence_kind", "observed_at"),
    )


# ===================================================================== actors ==


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A company, agency, utility, or - flagged and redacted - a private individual.

    Helios's ethics posture depends on ``is_natural_person``: rows so flagged have
    their identifying detail suppressed at ingestion and are never exposed
    through the public API.
    """

    __tablename__ = "organizations"

    canonical_name: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    """Case-folded, suffix-stripped name used as the entity-resolution blocking key."""

    role: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    organization_type: Mapped[str | None] = mapped_column(String(60))
    """Legal form inferred from the name suffix: LLC, INC, LP, TRUST."""

    is_natural_person: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_redacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """Set when PII policy suppressed the stored detail."""

    is_suspected_shell: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shell_indicators: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    jurisdiction_of_formation: Mapped[str | None] = mapped_column(String(80))
    registry_id: Mapped[str | None] = mapped_column(String(120))
    formation_date: Mapped[date | None] = mapped_column(Date)

    mailing_address: Mapped[str | None] = mapped_column(Text)
    mailing_city: Mapped[str | None] = mapped_column(String(120))
    mailing_state: Mapped[str | None] = mapped_column(String(40))
    mailing_postal_code: Mapped[str | None] = mapped_column(String(20))

    website: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    aliases: Mapped[list[OrganizationAlias]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_organizations_normalized_role", "normalized_name", "role"),
        Index(
            "ix_organizations_name_trgm",
            "normalized_name",
            postgresql_using="gin",
            postgresql_ops={"normalized_name": "gin_trgm_ops"},
        ),
    )


class OrganizationAlias(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An alternate spelling of an organization name observed in a source."""

    __tablename__ = "organization_aliases"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(400), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL")
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint("organization_id", "normalized_alias", name="organization_alias_unique"),
    )


class OrganizationRelationship(UUIDPrimaryKeyMixin, TimestampMixin, EffectiveDatingMixin, Base):
    """A time-bounded, evidence-backed edge between two organizations.

    Confidence is stored on the edge rather than the node: Helios can be certain
    that an LLC exists while being highly uncertain about who controls it.
    """

    __tablename__ = "organization_relationships"

    from_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    assertion_class: Mapped[str] = mapped_column(String(20), nullable=False, default="inferred")
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    human_review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_reviewed"
    )

    evidence_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="SET NULL")
    )
    supporting_features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    contradicting_features: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="rel_confidence_range"),
        CheckConstraint("from_organization_id <> to_organization_id", name="no_self_relationship"),
        UniqueConstraint(
            "from_organization_id",
            "to_organization_id",
            "relationship_type",
            "effective_start",
            name="organization_relationship_unique",
        ),
    )


# ============================================================= physical world ==


class Parcel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tax parcel with geometry, current owner, and assessor attributes."""

    __tablename__ = "parcels"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    apn: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    """Assessor parcel number, normalised to digits only for joining."""

    apn_formatted: Mapped[str | None] = mapped_column(String(40))
    county: Mapped[str] = mapped_column(String(80), nullable=False, default="Maricopa")
    jurisdiction: Mapped[str | None] = mapped_column(String(120), index=True)

    situs_address: Mapped[str | None] = mapped_column(Text)
    situs_city: Mapped[str | None] = mapped_column(String(120), index=True)
    situs_postal_code: Mapped[str | None] = mapped_column(String(20))

    owner_name_raw: Mapped[str | None] = mapped_column(String(400))
    """As printed by the assessor. NULL when redacted under PII policy."""

    owner_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    owner_is_redacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    land_use_code: Mapped[str | None] = mapped_column(String(20), index=True)
    land_use_description: Mapped[str | None] = mapped_column(String(200), index=True)
    legal_class_code: Mapped[str | None] = mapped_column(String(20))

    lot_size_acres: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), index=True)
    lot_size_sqft: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    construction_year: Mapped[int | None] = mapped_column(SmallInteger)

    last_deed_number: Mapped[str | None] = mapped_column(String(60))
    last_deed_date: Mapped[date | None] = mapped_column(Date, index=True)
    last_deed_url: Mapped[str | None] = mapped_column(Text)
    last_sale_date: Mapped[date | None] = mapped_column(Date, index=True)
    last_sale_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    assessor_url: Mapped[str | None] = mapped_column(Text)
    geometry: Mapped[Any | None] = mapped_column(_Polygon)
    centroid: Mapped[Any | None] = mapped_column(_Point)

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    ownership_events: Mapped[list[ParcelOwnershipEvent]] = relationship(
        back_populates="parcel",
        cascade="all, delete-orphan",
        order_by="ParcelOwnershipEvent.event_date",
    )
    site_links: Mapped[list[SiteParcelLink]] = relationship(back_populates="parcel")

    __table_args__ = (
        UniqueConstraint("source_id", "apn", name="parcel_apn_unique"),
        CheckConstraint(
            "lot_size_acres IS NULL OR lot_size_acres >= 0", name="lot_size_non_negative"
        ),
        Index("ix_parcels_geometry", "geometry", postgresql_using="gist"),
        Index("ix_parcels_centroid", "centroid", postgresql_using="gist"),
        Index("ix_parcels_city_use", "situs_city", "land_use_description"),
    )


class ParcelOwnershipEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recorded transfer or ownership observation for a parcel.

    Note that the Maricopa assessor feed exposes only the *most recent* deed, so
    Helios observes a truncated chain. This is a documented recall limitation,
    not a modelling one - the table supports full chains when a source provides
    them.
    """

    __tablename__ = "parcel_ownership_events"

    parcel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, default="deed_transfer")
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    owner_name_raw: Mapped[str | None] = mapped_column(String(400))
    owner_is_redacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    deed_number: Mapped[str | None] = mapped_column(String(60))
    deed_url: Mapped[str | None] = mapped_column(Text)
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    assertion_class: Mapped[str] = mapped_column(String(20), nullable=False, default="reported")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.9)
    evidence_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="SET NULL")
    )

    parcel: Mapped[Parcel] = relationship(back_populates="ownership_events")

    __table_args__ = (
        UniqueConstraint(
            "parcel_id", "event_date", "deed_number", name="parcel_ownership_event_unique"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ownership_confidence_range"),
    )


class Site(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A suspected or confirmed development site.

    A site is an *analytical construct*, not a public record: it is Helios's
    hypothesis that a set of parcels constitutes one project. The anonymous
    ``project_code`` is used in preference to a company name precisely because
    naming an operator on weak evidence is the failure mode this project most
    wants to avoid.
    """

    __tablename__ = "sites"

    project_code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    """Stable anonymous identifier, e.g. ``AZ-MESA-017``."""

    display_name: Mapped[str | None] = mapped_column(String(300))
    site_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    site_kind_assertion: Mapped[str] = mapped_column(String(20), nullable=False, default="inferred")

    jurisdiction: Mapped[str | None] = mapped_column(String(120), index=True)
    county: Mapped[str] = mapped_column(String(80), nullable=False, default="Maricopa")
    region_slug: Mapped[str] = mapped_column(
        String(80), nullable=False, default="east-valley-az", index=True
    )

    current_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, index=True)
    current_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage_last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_last_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    operator_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    operator_assertion: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    """Almost always ``unknown``. Helios does not name operators without a direct filing."""

    first_signal_date: Mapped[date | None] = mapped_column(Date, index=True)
    latest_signal_date: Mapped[date | None] = mapped_column(Date, index=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    total_acres: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    boundary: Mapped[Any | None] = mapped_column(_Polygon)
    centroid: Mapped[Any | None] = mapped_column(_Point)

    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    parcel_links: Mapped[list[SiteParcelLink]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    stage_history: Mapped[list[SiteStageHistory]] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        order_by="SiteStageHistory.effective_date",
    )
    evidence_records: Mapped[list[EvidenceRecord]] = relationship(back_populates="site")
    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    estimates: Mapped[list[SiteEstimate]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )
    dependencies: Mapped[list[InfrastructureDependency]] = relationship(
        back_populates="site", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("current_stage >= 0 AND current_stage <= 8", name="stage_range"),
        CheckConstraint(
            "current_confidence >= 0 AND current_confidence <= 100", name="site_confidence_range"
        ),
        Index("ix_sites_boundary", "boundary", postgresql_using="gist"),
        Index("ix_sites_centroid", "centroid", postgresql_using="gist"),
        Index("ix_sites_region_stage", "region_slug", "current_stage"),
    )


class SiteParcelLink(UUIDPrimaryKeyMixin, TimestampMixin, EffectiveDatingMixin, Base):
    """Association of a parcel with a site, with the reason it was linked."""

    __tablename__ = "site_parcel_links"

    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parcel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parcels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_reason: Mapped[str] = mapped_column(String(60), nullable=False)
    """``assessor_classification``, ``shared_owner``, ``adjacency``, ``manual``."""

    match_method: Mapped[str] = mapped_column(String(40), nullable=False)
    spatial_confidence: Mapped[float | None] = mapped_column(Float)
    distance_meters: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    human_review_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_reviewed"
    )

    site: Mapped[Site] = relationship(back_populates="parcel_links")
    parcel: Mapped[Parcel] = relationship(back_populates="site_links")

    __table_args__ = (
        UniqueConstraint("site_id", "parcel_id", name="site_parcel_unique"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="link_confidence_range"),
    )


class SiteStageHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An append-only record of every stage transition for a site.

    Downgrades are legitimate and expected when evidence is contradicted, so this
    table is not constrained to monotonic progression - but nothing is ever
    deleted, which is what makes "how did this conclusion change?" answerable.
    """

    __tablename__ = "site_stage_history"

    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage: Mapped[int | None] = mapped_column(SmallInteger)
    to_stage: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    """When the transition is believed to have occurred, from evidence dates."""

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """When Helios noticed. The gap between this and ``effective_date`` is detection lag."""

    is_downgrade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    triggering_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )

    site: Mapped[Site] = relationship(back_populates="stage_history")

    __table_args__ = (
        CheckConstraint("to_stage >= 0 AND to_stage <= 8", name="to_stage_range"),
        CheckConstraint(
            "from_stage IS NULL OR (from_stage >= 0 AND from_stage <= 8)", name="from_stage_range"
        ),
        Index("ix_stage_history_site_effective", "site_id", "effective_date"),
    )


class Substation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An electrical substation, the single strongest infrastructure signal."""

    __tablename__ = "substations"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_native_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str | None] = mapped_column(String(300), index=True)
    operator_name: Mapped[str | None] = mapped_column(String(300), index=True)
    operator_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )

    max_voltage_kv: Mapped[float | None] = mapped_column(Float, index=True)
    voltages_kv: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    substation_function: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str | None] = mapped_column(String(40))

    geometry: Mapped[Any | None] = mapped_column(_Polygon)
    location: Mapped[Any | None] = mapped_column(_Point)

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "source_native_id", name="substation_native_unique"),
        Index("ix_substations_location", "location", postgresql_using="gist"),
        Index("ix_substations_geometry", "geometry", postgresql_using="gist"),
    )


class TransmissionLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A transmission or subtransmission circuit."""

    __tablename__ = "transmission_lines"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_native_id: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str | None] = mapped_column(String(300))
    operator_name: Mapped[str | None] = mapped_column(String(300), index=True)

    voltage_kv: Mapped[float | None] = mapped_column(Float, index=True)
    circuit_count: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str | None] = mapped_column(String(40))
    geometry: Mapped[Any | None] = mapped_column(_Line)

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "source_native_id", name="transmission_native_unique"),
        Index("ix_transmission_lines_geometry", "geometry", postgresql_using="gist"),
    )


class InfrastructureDependency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An edge asserting that a site depends on a piece of infrastructure."""

    __tablename__ = "infrastructure_dependencies"

    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    infrastructure_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    substation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("substations.id", ondelete="SET NULL")
    )
    transmission_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transmission_lines.id", ondelete="SET NULL")
    )
    permit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("permits.id", ondelete="SET NULL")
    )

    label: Mapped[str] = mapped_column(String(300), nullable=False)
    dependency_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    """True when the site cannot operate until this dependency is satisfied."""

    match_method: Mapped[str | None] = mapped_column(String(40))
    distance_meters: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    assertion_class: Mapped[str] = mapped_column(String(20), nullable=False, default="inferred")
    evidence_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site] = relationship(back_populates="dependencies")

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="dependency_confidence_range"),
        Index("ix_dependencies_site_kind", "site_id", "infrastructure_kind"),
    )


# ================================================================= regulatory ==


class Permit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A permit, licence, or registration issued by a public body."""

    __tablename__ = "permits"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_native_id: Mapped[str] = mapped_column(String(200), nullable=False)
    permit_number: Mapped[str | None] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    permit_type_raw: Mapped[str | None] = mapped_column(String(200))
    """The agency's own type string, preserved so normalization is auditable."""

    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(120))
    issuing_authority: Mapped[str | None] = mapped_column(String(200))
    jurisdiction: Mapped[str | None] = mapped_column(String(120), index=True)

    applied_date: Mapped[date | None] = mapped_column(Date, index=True)
    issued_date: Mapped[date | None] = mapped_column(Date, index=True)
    status_date: Mapped[date | None] = mapped_column(Date)
    expiration_date: Mapped[date | None] = mapped_column(Date)

    address_raw: Mapped[str | None] = mapped_column(Text)
    parcel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("parcels.id", ondelete="SET NULL"), index=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"), index=True
    )
    applicant_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )

    location: Mapped[Any | None] = mapped_column(_Point)
    valuation: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("source_id", "source_native_id", name="permit_native_unique"),
        Index("ix_permits_location", "location", postgresql_using="gist"),
        Index("ix_permits_category_issued", "category", "issued_date"),
    )


# =================================================================== analysis ==


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned, immutable snapshot of a scoring or classification model.

    Scores are meaningless without knowing which rule set produced them, so every
    prediction references one of these and the parameters are stored inline.
    """

    __tablename__ = "model_versions"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="rule_based")
    description: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    calibration_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("name", "version", name="model_version_unique"),)


class Prediction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A scored, explained prediction about a site at a point in time.

    Predictions are append-only: recalculating produces a new row, which is what
    makes the "how did this score change?" view possible.
    """

    __tablename__ = "predictions"

    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    prediction_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="site_confidence"
    )

    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    """Evidence cutoff used. Backtest replays set this to a historical date."""

    predicted_stage: Mapped[int | None] = mapped_column(SmallInteger)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_band: Mapped[str] = mapped_column(String(20), nullable=False)

    positive_contribution: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    negative_contribution: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_considered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_evidence_kinds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site] = relationship(back_populates="predictions")
    explanations: Mapped[list[PredictionExplanation]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="prediction_conf_range"),
        Index("ix_predictions_site_calculated", "site_id", "calculated_at"),
    )


class PredictionExplanation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One evidence contribution to a prediction - the 'why' row.

    Every point of every score is attributable to exactly one of these, and each
    carries the evidence record it came from.
    """

    __tablename__ = "prediction_explanations"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_records.id", ondelete="SET NULL"), index=True
    )
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_kind: Mapped[str | None] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)

    base_weight: Mapped[float] = mapped_column(Float, nullable=False)
    applied_weight: Mapped[float] = mapped_column(Float, nullable=False)
    """Weight after confidence and recency multipliers - what actually hit the score."""

    confidence_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    recency_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False, default="supporting")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    prediction: Mapped[Prediction] = relationship(back_populates="explanations")


class SiteEstimate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A ranged, method-documented estimate such as power demand.

    Always a range with stated assumptions. A point estimate would imply a
    precision the evidence does not support.
    """

    __tablename__ = "site_estimates"

    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    estimate_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)

    lower_value: Mapped[float | None] = mapped_column(Float)
    likely_value: Mapped[float | None] = mapped_column(Float)
    upper_value: Mapped[float | None] = mapped_column(Float)

    method: Mapped[str] = mapped_column(String(120), nullable=False)
    assertion_class: Mapped[str] = mapped_column(String(20), nullable=False, default="estimated")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    evidence_record_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL")
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    site: Mapped[Site] = relationship(back_populates="estimates")

    __table_args__ = (
        CheckConstraint(
            "lower_value IS NULL OR upper_value IS NULL OR lower_value <= upper_value",
            name="estimate_bounds_ordered",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="estimate_confidence_range"),
    )


class HumanReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An audit record of a human accepting, rejecting, or amending a machine output."""

    __tablename__ = "human_reviews"

    target_table: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(30))
    rationale: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_human_reviews_target", "target_table", "target_id"),)


__all__ = [
    "ConnectorRun",
    "DocumentVersion",
    "EvidenceRecord",
    "HumanReview",
    "InfrastructureDependency",
    "IngestionFailure",
    "ModelVersion",
    "Organization",
    "OrganizationAlias",
    "OrganizationRelationship",
    "Parcel",
    "ParcelOwnershipEvent",
    "Permit",
    "Prediction",
    "PredictionExplanation",
    "Site",
    "SiteEstimate",
    "SiteParcelLink",
    "SiteStageHistory",
    "Source",
    "SourceConnector",
    "SourceDocument",
    "Substation",
    "TransmissionLine",
]
