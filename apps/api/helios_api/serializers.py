"""Conversion from ORM rows to API schemas.

Kept apart from the route handlers so that the mapping - especially the parts
that decide what is safe to expose - is in one reviewable place. Two rules are
enforced here rather than trusted to callers:

* Redacted owner names are never emitted, even though the column may be
  populated when the PII policy was disabled during ingestion.
* Licence attributions are collected from the sources behind each response, so
  ODbL obligations travel with the data.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from geoalchemy2.shape import to_shape
from sqlalchemy import select

from helios_api.schemas import (
    DependencyResponse,
    DocumentVersionResponse,
    EstimateResponse,
    EvidenceItemResponse,
    OrganizationSummary,
    ParcelSummary,
    PredictionResponse,
    ScoreExplanation,
    SiteSummary,
    SourceReference,
    StageTransition,
)
from helios_common.vocabulary import ConfidenceBand
from helios_domain.models import (
    DocumentVersion,
    EvidenceRecord,
    Prediction,
    Site,
    SiteStageHistory,
    Source,
    SourceDocument,
)
from helios_domain.ontology import DevelopmentStage

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def geometry_to_geojson(geometry: Any) -> dict[str, Any] | None:
    """Convert a PostGIS geometry column value to a GeoJSON dictionary."""
    if geometry is None:
        return None
    shape = to_shape(geometry)
    return json.loads(json.dumps(shape.__geo_interface__))


def geometry_to_point(geometry: Any) -> list[float] | None:
    """Convert a PostGIS point to ``[longitude, latitude]``."""
    if geometry is None:
        return None
    shape = to_shape(geometry)
    return [round(shape.x, 6), round(shape.y, 6)]


def serialize_site_summary(site: Site, *, parcel_count: int = 0) -> SiteSummary:
    """Map a site row onto its list representation."""
    stage = DevelopmentStage(site.current_stage)
    return SiteSummary(
        id=site.id,
        project_code=site.project_code,
        display_name=site.display_name,
        site_kind=site.site_kind,
        site_kind_assertion=site.site_kind_assertion,
        jurisdiction=site.jurisdiction,
        county=site.county,
        region_slug=site.region_slug,
        current_stage=site.current_stage,
        current_stage_label=stage.label,
        current_confidence=round(site.current_confidence, 2),
        confidence_band=str(ConfidenceBand.from_score(site.current_confidence)),
        first_signal_date=site.first_signal_date,
        latest_signal_date=site.latest_signal_date,
        evidence_count=site.evidence_count,
        total_acres=float(site.total_acres) if site.total_acres is not None else None,
        parcel_count=parcel_count,
        operator_status=(
            "not_established" if site.operator_organization_id is None else site.operator_assertion
        ),
        stage_last_changed_at=site.stage_last_changed_at,
        score_last_calculated_at=site.score_last_calculated_at,
        centroid=geometry_to_point(site.centroid),
        is_synthetic=site.is_synthetic,
    )


def serialize_parcel(parcel: Any, link: Any = None) -> ParcelSummary:
    """Map a parcel row, honouring redaction regardless of what is stored."""
    return ParcelSummary(
        id=parcel.id,
        apn=parcel.apn,
        apn_formatted=parcel.apn_formatted,
        situs_address=parcel.situs_address,
        situs_city=parcel.situs_city,
        # Belt and braces: even if a name was stored under a disabled policy, the
        # API refuses to serve one flagged as redacted.
        owner_name=None if parcel.owner_is_redacted else parcel.owner_name_raw,
        owner_is_redacted=parcel.owner_is_redacted,
        land_use_description=parcel.land_use_description,
        lot_size_acres=(
            float(parcel.lot_size_acres) if parcel.lot_size_acres is not None else None
        ),
        last_deed_date=parcel.last_deed_date,
        last_deed_number=parcel.last_deed_number,
        last_deed_url=parcel.last_deed_url,
        last_sale_price=(
            float(parcel.last_sale_price) if parcel.last_sale_price is not None else None
        ),
        assessor_url=parcel.assessor_url,
        link_reason=link.link_reason if link else None,
        link_confidence=link.confidence if link else None,
    )


def serialize_organization(organization: Any) -> OrganizationSummary:
    """Map an organization row.

    Natural-person rows are never created during ingestion, so this path cannot
    expose an individual. The role is still surfaced so a reviewer can spot a
    misclassification.
    """
    indicators = (organization.shell_indicators or {}).get("indicators", [])
    return OrganizationSummary(
        id=organization.id,
        canonical_name=organization.canonical_name,
        role=organization.role,
        organization_type=organization.organization_type,
        is_suspected_shell=organization.is_suspected_shell,
        shell_indicators=list(indicators),
        mailing_city=organization.mailing_city,
        mailing_state=organization.mailing_state,
    )


def serialize_source_reference(
    document: SourceDocument, version: DocumentVersion, source: Source
) -> SourceReference:
    """Build the provenance pointer attached to every evidence record."""
    return SourceReference(
        document_id=document.id,
        document_version_id=version.id,
        source_slug=source.slug,
        source_name=source.name,
        agency=source.agency,
        source_url=document.source_url,
        retrieved_at=version.retrieved_at,
        content_sha256=version.content_sha256,
        parser_version=version.parser_version,
        attribution_text=source.attribution_text if source.attribution_required else None,
    )


def serialize_evidence(session: Session, record: EvidenceRecord) -> EvidenceItemResponse:
    """Map an evidence record together with its provenance."""
    version = session.get(DocumentVersion, record.document_version_id)
    document = session.get(SourceDocument, record.document_id)
    if version is None or document is None:  # pragma: no cover - FK guarantees these
        raise LookupError(f"Evidence {record.id} has a dangling provenance reference")
    source = session.get(Source, document.source_id)
    if source is None:  # pragma: no cover
        raise LookupError(f"Document {document.id} has no source")

    return EvidenceItemResponse(
        id=record.id,
        evidence_kind=record.evidence_kind,
        summary=record.summary,
        snippet=record.snippet,
        snippet_locator=record.snippet_locator,
        observed_at=record.observed_at,
        assertion_class=record.assertion_class,
        extraction_method=record.extraction_method,
        polarity=record.polarity,
        confidence=record.confidence,
        human_review_status=record.human_review_status,
        is_standing_condition=bool(
            (record.normalized_values or {}).get("is_standing_condition", False)
        ),
        normalized_values=record.normalized_values or {},
        source=serialize_source_reference(document, version, source),
    )


def serialize_stage_transition(history: SiteStageHistory) -> StageTransition:
    """Map a stage-history row, including the detection lag."""
    from_stage = DevelopmentStage(history.from_stage) if history.from_stage is not None else None
    to_stage = DevelopmentStage(history.to_stage)
    lag = (history.detected_at.date() - history.effective_date).days
    return StageTransition(
        id=history.id,
        from_stage=history.from_stage,
        from_stage_label=from_stage.label if from_stage else None,
        to_stage=history.to_stage,
        to_stage_label=to_stage.label,
        effective_date=history.effective_date,
        detected_at=history.detected_at,
        is_downgrade=history.is_downgrade,
        confidence=history.confidence,
        rationale=history.rationale,
        triggering_evidence_ids=list(history.triggering_evidence_ids or []),
        detection_lag_days=lag,
    )


def serialize_prediction(session: Session, prediction: Prediction) -> PredictionResponse:
    """Map a prediction with its ordered explanations."""
    from helios_domain.models import ModelVersion, PredictionExplanation

    model = session.get(ModelVersion, prediction.model_version_id)
    explanations = session.scalars(
        select(PredictionExplanation)
        .where(PredictionExplanation.prediction_id == prediction.id)
        .order_by(PredictionExplanation.display_order)
    ).all()

    stage = (
        DevelopmentStage(prediction.predicted_stage)
        if prediction.predicted_stage is not None
        else None
    )

    return PredictionResponse(
        id=prediction.id,
        calculated_at=prediction.calculated_at,
        as_of_date=prediction.as_of_date,
        predicted_stage=prediction.predicted_stage,
        predicted_stage_label=stage.label if stage else None,
        raw_score=prediction.raw_score,
        confidence=prediction.confidence,
        confidence_band=prediction.confidence_band,
        positive_contribution=prediction.positive_contribution,
        negative_contribution=prediction.negative_contribution,
        evidence_considered=prediction.evidence_considered,
        distinct_evidence_kinds=prediction.distinct_evidence_kinds,
        is_backtest=prediction.is_backtest,
        summary=prediction.summary,
        model_name=model.name if model else "unknown",
        model_version=model.version if model else "unknown",
        explanations=[
            ScoreExplanation(
                rule_id=e.rule_id,
                evidence_kind=e.evidence_kind,
                label=e.label,
                detail=e.detail,
                base_weight=e.base_weight,
                applied_weight=e.applied_weight,
                confidence_multiplier=e.confidence_multiplier,
                recency_multiplier=e.recency_multiplier,
                polarity=e.polarity,
                evidence_record_id=e.evidence_record_id,
            )
            for e in explanations
        ],
    )


def serialize_dependency(session: Session, dependency: Any) -> DependencyResponse:
    """Map an infrastructure dependency, enriching it from the target row."""
    from helios_domain.models import Substation, TransmissionLine

    voltage: float | None = None
    operator: str | None = None
    if dependency.substation_id:
        substation = session.get(Substation, dependency.substation_id)
        if substation:
            voltage = substation.max_voltage_kv
            operator = substation.operator_name
    elif dependency.transmission_line_id:
        line = session.get(TransmissionLine, dependency.transmission_line_id)
        if line:
            voltage = line.voltage_kv
            operator = line.operator_name

    return DependencyResponse(
        id=dependency.id,
        infrastructure_kind=dependency.infrastructure_kind,
        label=dependency.label,
        dependency_status=dependency.dependency_status,
        is_blocking=dependency.is_blocking,
        match_method=dependency.match_method,
        distance_meters=dependency.distance_meters,
        confidence=dependency.confidence,
        assertion_class=dependency.assertion_class,
        notes=dependency.notes,
        voltage_kv=voltage,
        operator_name=operator,
    )


def serialize_estimate(estimate: Any) -> EstimateResponse:
    """Map a ranged estimate."""
    return EstimateResponse(
        id=estimate.id,
        estimate_type=estimate.estimate_type,
        unit=estimate.unit,
        lower_value=estimate.lower_value,
        likely_value=estimate.likely_value,
        upper_value=estimate.upper_value,
        method=estimate.method,
        assertion_class=estimate.assertion_class,
        confidence=estimate.confidence,
        assumptions=estimate.assumptions or {},
        calculated_at=estimate.calculated_at,
        notes=estimate.notes,
    )


def serialize_document_version(version: DocumentVersion) -> DocumentVersionResponse:
    """Map a document version."""
    return DocumentVersionResponse(
        id=version.id,
        version_number=version.version_number,
        content_sha256=version.content_sha256,
        content_length=version.content_length,
        mime_type=version.mime_type,
        retrieved_at=version.retrieved_at,
        source_url=version.source_url,
        http_status=version.http_status,
        etag=version.etag,
        connector_version=version.connector_version,
        parser_version=version.parser_version,
        supersedes_version_id=version.supersedes_version_id,
    )


def collect_attributions(session: Session, site_id: Any) -> list[str]:
    """Gather licence attributions required by the sources behind a site.

    ODbL and similar licences make attribution a condition of use, so it travels
    with every response rather than living only in a footer somewhere.
    """
    rows = session.execute(
        select(Source.attribution_text)
        .distinct()
        .join(SourceDocument, SourceDocument.source_id == Source.id)
        .join(EvidenceRecord, EvidenceRecord.document_id == SourceDocument.id)
        .where(EvidenceRecord.site_id == site_id, Source.attribution_required.is_(True))
    ).scalars()
    return [row for row in rows if row]


__all__ = [
    "collect_attributions",
    "geometry_to_geojson",
    "geometry_to_point",
    "serialize_dependency",
    "serialize_document_version",
    "serialize_estimate",
    "serialize_evidence",
    "serialize_organization",
    "serialize_parcel",
    "serialize_prediction",
    "serialize_site_summary",
    "serialize_source_reference",
    "serialize_stage_transition",
]
