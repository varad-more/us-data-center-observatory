"""Regional analytics and data-quality measurement."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from helios_api.deps import DbSession
from helios_api.schemas import (
    AnalyticsStagesResponse,
    ProvenanceCompletenessResponse,
    StageDistributionEntry,
)
from helios_domain.models import EvidenceRecord, Site
from helios_domain.ontology import DevelopmentStage

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/stages",
    response_model=AnalyticsStagesResponse,
    summary="Distribution of sites across development stages",
)
def stage_distribution(
    session: DbSession,
    region: Annotated[str | None, Query(description="Region slug filter")] = None,
) -> AnalyticsStagesResponse:
    """Return how many sites sit at each stage, with mean confidence."""
    statement = select(
        Site.current_stage,
        func.count().label("site_count"),
        func.avg(Site.current_confidence).label("mean_confidence"),
    ).group_by(Site.current_stage)
    if region:
        statement = statement.where(Site.region_slug == region)

    rows = {row.current_stage: row for row in session.execute(statement).all()}

    stages = [
        StageDistributionEntry(
            stage=int(stage),
            stage_label=stage.label,
            site_count=rows[int(stage)].site_count if int(stage) in rows else 0,
            mean_confidence=(
                round(float(rows[int(stage)].mean_confidence), 2)
                if int(stage) in rows and rows[int(stage)].mean_confidence is not None
                else None
            ),
        )
        for stage in DevelopmentStage
    ]

    total = sum(s.site_count for s in stages)
    return AnalyticsStagesResponse(region_slug=region, total_sites=total, stages=stages)


@router.get(
    "/provenance",
    response_model=ProvenanceCompletenessResponse,
    summary="Measured provenance completeness",
)
def provenance_completeness(session: DbSession) -> ProvenanceCompletenessResponse:
    """Measure what fraction of evidence carries complete provenance.

    The target is 100%. Publishing the measurement rather than asserting the
    property means a regression shows up as a number instead of an unnoticed
    erosion of the system's central guarantee.
    """
    total = session.scalar(select(func.count()).select_from(EvidenceRecord)) or 0

    def _count(condition: Any) -> int:
        return (
            session.scalar(select(func.count()).select_from(EvidenceRecord).where(condition)) or 0
        )

    with_version = _count(EvidenceRecord.document_version_id.isnot(None))
    with_snippet = _count(EvidenceRecord.snippet.isnot(None) & (EvidenceRecord.snippet != ""))
    with_locator = _count(EvidenceRecord.snippet_locator.isnot(None))
    with_date = _count(EvidenceRecord.observed_at.isnot(None))

    complete = min(with_version, with_snippet, with_locator, with_date)
    ratio = round(complete / total, 4) if total else 1.0

    return ProvenanceCompletenessResponse(
        total_evidence_records=total,
        with_document_version=with_version,
        with_snippet=with_snippet,
        with_locator=with_locator,
        with_observation_date=with_date,
        completeness_ratio=ratio,
        note=(
            "An evidence record counts as complete only when it cites an immutable "
            "document version, quotes a snippet, names a locator within that document, "
            "and carries an observation date."
        ),
    )


__all__ = ["router"]
