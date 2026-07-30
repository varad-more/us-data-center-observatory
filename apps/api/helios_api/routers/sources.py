"""Source-registry and connector-health endpoints.

Publishing the registry - including the sources Helios cannot read - is a
deliberate transparency feature. A user looking at a site with thin evidence
should be able to see whether that reflects a quiet project or a blocked source.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from helios_api.deps import DbSession
from helios_api.schemas import (
    ConnectorRunResponse,
    DocumentResponse,
    DocumentVersionResponse,
    LargeLoadFilingListResponse,
    LargeLoadFilingResponse,
    SourceListResponse,
    SourceReference,
    SourceResponse,
)
from helios_api.serializers import serialize_document_version
from helios_domain.models import (
    ConnectorRun,
    DocumentVersion,
    EvidenceRecord,
    Source,
    SourceConnector,
    SourceDocument,
)

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=SourceListResponse, summary="The source registry")
def list_sources(session: DbSession) -> SourceListResponse:
    """Return every declared source with its licensing and connector status."""
    sources = session.scalars(select(Source).order_by(Source.category, Source.name)).all()

    items: list[SourceResponse] = []
    coverage: dict[str, int] = {}

    for source in sources:
        connector = session.scalars(
            select(SourceConnector).where(SourceConnector.source_id == source.id).limit(1)
        ).first()
        document_count = (
            session.scalar(
                select(func.count())
                .select_from(SourceDocument)
                .where(SourceDocument.source_id == source.id)
            )
            or 0
        )
        # The source carries its own status and limitation. Falling back to the
        # connector row would report every unreadable source as "planned" and
        # drop the explanation of what actually blocks it.
        connector_status = source.connector_status
        coverage[connector_status] = coverage.get(connector_status, 0) + 1

        items.append(
            SourceResponse(
                id=source.id,
                slug=source.slug,
                name=source.name,
                agency=source.agency,
                jurisdiction=source.jurisdiction,
                category=source.category,
                base_url=source.base_url,
                access_method=source.access_method,
                update_frequency=source.update_frequency,
                license_name=source.license_name,
                license_url=source.license_url,
                attribution_required=source.attribution_required,
                attribution_text=source.attribution_text,
                robots_policy_status=source.robots_policy_status,
                geographic_coverage=source.geographic_coverage,
                historical_coverage=source.historical_coverage,
                contains_personal_data=source.contains_personal_data,
                reliability_score=source.reliability_score,
                known_schema_issues=source.known_schema_issues,
                notes=source.notes,
                connector_status=connector_status,
                connector_slug=connector.slug if connector else None,
                access_limitation=source.access_limitation,
                last_success_at=connector.last_success_at if connector else None,
                document_count=document_count,
            )
        )

    return SourceListResponse(items=items, coverage_summary=coverage)


def _evidence_fields(evidence: EvidenceRecord) -> dict[str, dict[str, object]]:
    """Index the normalized field payload stored on one evidence record."""
    values = evidence.normalized_values or {}
    fields = values.get("fields")
    if not isinstance(fields, list):
        return {}
    return {
        str(field["name"]): field
        for field in fields
        if isinstance(field, dict) and field.get("name")
    }


def _required_evidence_value(
    fields: dict[str, dict[str, object]], evidence_id: UUID, name: str
) -> object:
    """Return one normalized field value, failing on corrupt published evidence."""
    field = fields.get(name)
    if field is None or "value" not in field:
        raise RuntimeError(f"Large-load evidence {evidence_id} is missing required field {name!r}")
    return field["value"]


def _required_evidence_float(
    fields: dict[str, dict[str, object]], evidence_id: UUID, name: str
) -> float:
    """Return one numeric normalized field without silently coercing booleans."""
    raw = _required_evidence_value(fields, evidence_id, name)
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise RuntimeError(f"Large-load evidence {evidence_id} field {name!r} is not numeric")
    return float(raw)


@router.get(
    "/large-load-filings",
    response_model=LargeLoadFilingListResponse,
    summary="State-regulator filings with reported large loads",
)
def list_large_load_filings(session: DbSession) -> LargeLoadFilingListResponse:
    """Return site-specific load disclosures without inventing exact geometry."""
    evidence_rows = session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.evidence_kind == "large_load_service_contract")
        .order_by(EvidenceRecord.observed_at.desc(), EvidenceRecord.id)
    ).all()

    items: list[LargeLoadFilingResponse] = []
    for evidence in evidence_rows:
        document = evidence.document
        source = document.source
        version = session.get(DocumentVersion, evidence.document_version_id)
        if version is None:
            continue
        fields = _evidence_fields(evidence)
        load_field = fields.get("reported_load_mw") or {}
        parent_field = fields.get("parent_company_name") or {}
        items.append(
            LargeLoadFilingResponse(
                evidence_id=evidence.id,
                docket_number=str(_required_evidence_value(fields, evidence.id, "docket_number")),
                decision_date=evidence.observed_at,
                decision_status="conditionally_approved",
                utility_name=str(_required_evidence_value(fields, evidence.id, "utility_name")),
                customer_name=str(_required_evidence_value(fields, evidence.id, "customer_name")),
                parent_company_name=(
                    str(parent_field["value"]) if parent_field.get("value") else None
                ),
                project_type="data_center",
                reported_load_mw=_required_evidence_float(fields, evidence.id, "reported_load_mw"),
                load_assertion_class=str(load_field.get("assertion_class") or "unknown"),
                location_name=str(_required_evidence_value(fields, evidence.id, "location_name")),
                county_name=str(_required_evidence_value(fields, evidence.id, "county_name")),
                state_code=str(_required_evidence_value(fields, evidence.id, "state_code")),
                location_precision=str(
                    _required_evidence_value(fields, evidence.id, "location_precision")
                ),
                geometry=None,
                summary=evidence.summary,
                snippet=evidence.snippet or "",
                snippet_locator=evidence.snippet_locator,
                evidence_assertion_class=evidence.assertion_class,
                source=SourceReference(
                    document_id=document.id,
                    document_version_id=version.id,
                    source_slug=source.slug,
                    source_name=source.name,
                    agency=source.agency,
                    source_url=document.source_url,
                    retrieved_at=version.retrieved_at,
                    content_sha256=version.content_sha256,
                    parser_version=version.parser_version,
                    attribution_text=source.attribution_text,
                ),
            )
        )

    return LargeLoadFilingListResponse(
        items=items,
        note=(
            "These are filing-level records. A named township is not an exact "
            "facility location, so records without parcel evidence carry no geometry."
        ),
    )


@router.get(
    "/connector-runs",
    response_model=list[ConnectorRunResponse],
    summary="Recent connector runs",
)
def list_connector_runs(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConnectorRunResponse]:
    """Return recent ingestion runs for the source-health dashboard."""
    runs = session.scalars(
        select(ConnectorRun).order_by(ConnectorRun.started_at.desc()).limit(limit)
    ).all()

    responses: list[ConnectorRunResponse] = []
    for run in runs:
        connector = session.get(SourceConnector, run.connector_id)
        responses.append(
            ConnectorRunResponse(
                id=run.id,
                connector_slug=connector.slug if connector else "unknown",
                started_at=run.started_at,
                finished_at=run.finished_at,
                duration_seconds=run.duration_seconds,
                status=run.status,
                mode=run.mode,
                items_discovered=run.items_discovered,
                items_fetched=run.items_fetched,
                items_parsed=run.items_parsed,
                items_normalized=run.items_normalized,
                items_rejected=run.items_rejected,
                items_unchanged=run.items_unchanged,
                versions_created=run.versions_created,
                evidence_created=run.evidence_created,
                schema_drift_detected=run.schema_drift_detected,
                message=run.message,
            )
        )
    return responses


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get a source document and its version history",
)
def get_document(session: DbSession, document_id: UUID) -> DocumentResponse:
    """Return a document with every immutable version Helios has retained."""
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No document with id {document_id}"
        )
    source = session.get(Source, document.source_id)
    versions = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number)
    ).all()

    return DocumentResponse(
        id=document.id,
        source_slug=source.slug if source else "unknown",
        source_name=source.name if source else "unknown",
        source_native_id=document.source_native_id,
        title=document.title,
        document_type=document.document_type,
        source_url=document.source_url,
        published_date=document.published_date,
        effective_date=document.effective_date,
        first_seen_at=document.first_seen_at,
        last_seen_at=document.last_seen_at,
        version_count=document.version_count,
        is_synthetic=document.is_synthetic,
        versions=[serialize_document_version(v) for v in versions],
    )


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[DocumentVersionResponse],
    summary="List a document's immutable versions",
)
def list_document_versions(session: DbSession, document_id: UUID) -> list[DocumentVersionResponse]:
    """Return every retained version of a document, oldest first."""
    if session.get(SourceDocument, document_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No document with id {document_id}"
        )
    versions = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number)
    ).all()
    return [serialize_document_version(v) for v in versions]


__all__ = ["router"]
