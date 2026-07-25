"""Site listing, detail, timeline, evidence, dependencies, and score history."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from helios_api.deps import BoundingBox, DbSession, PageParams
from helios_api.schemas import (
    DependencyResponse,
    EvidenceListResponse,
    PageMeta,
    ScoreHistoryResponse,
    SiteDetail,
    SiteListResponse,
    TimelineEntry,
    TimelineResponse,
)
from helios_api.serializers import (
    collect_attributions,
    geometry_to_geojson,
    serialize_dependency,
    serialize_estimate,
    serialize_evidence,
    serialize_organization,
    serialize_parcel,
    serialize_prediction,
    serialize_site_summary,
    serialize_stage_transition,
)
from helios_domain.models import (
    EvidenceRecord,
    InfrastructureDependency,
    Organization,
    Parcel,
    Prediction,
    Site,
    SiteEstimate,
    SiteParcelLink,
    SiteStageHistory,
)
from helios_domain.ontology import DevelopmentStage

router = APIRouter(prefix="/sites", tags=["sites"])


def _get_site_or_404(session: DbSession, site_id: UUID) -> Site:
    """Fetch a site or raise a 404."""
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No site with id {site_id}"
        )
    return site


def _parcel_count(session: DbSession, site_id: UUID) -> int:
    """Count parcels linked to a site."""
    return (
        session.scalar(
            select(func.count())
            .select_from(SiteParcelLink)
            .where(SiteParcelLink.site_id == site_id)
        )
        or 0
    )


@router.get("", response_model=SiteListResponse, summary="List sites")
def list_sites(
    session: DbSession,
    page: PageParams,
    bbox: BoundingBox = None,
    region: Annotated[str | None, Query(description="Region slug filter")] = None,
    jurisdiction: Annotated[str | None, Query()] = None,
    min_stage: Annotated[int | None, Query(ge=0, le=8)] = None,
    max_stage: Annotated[int | None, Query(ge=0, le=8)] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=100)] = None,
    sort: Annotated[str, Query(pattern="^-?(confidence|stage|acres|latest_signal)$")] = (
        "-confidence"
    ),
) -> SiteListResponse:
    """List sites with filtering, spatial bounding, sorting, and pagination."""
    statement = select(Site)

    if region:
        statement = statement.where(Site.region_slug == region)
    if jurisdiction:
        statement = statement.where(func.lower(Site.jurisdiction) == jurisdiction.lower())
    if min_stage is not None:
        statement = statement.where(Site.current_stage >= min_stage)
    if max_stage is not None:
        statement = statement.where(Site.current_stage <= max_stage)
    if min_confidence is not None:
        statement = statement.where(Site.current_confidence >= min_confidence)
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        statement = statement.where(
            func.ST_Intersects(
                Site.centroid,
                func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326),
            )
        )

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0

    descending = sort.startswith("-")
    key = sort.lstrip("-")
    column = {
        "confidence": Site.current_confidence,
        "stage": Site.current_stage,
        "acres": Site.total_acres,
        "latest_signal": Site.latest_signal_date,
    }[key]
    ordering = column.desc().nullslast() if descending else column.asc().nullsfirst()

    sites = session.scalars(
        statement.order_by(ordering, Site.project_code).limit(page.limit).offset(page.offset)
    ).all()

    return SiteListResponse(
        items=[serialize_site_summary(s, parcel_count=_parcel_count(session, s.id)) for s in sites],
        meta=PageMeta(
            total=total,
            limit=page.limit,
            offset=page.offset,
            has_more=page.offset + len(sites) < total,
        ),
    )


@router.get("/{site_id}", response_model=SiteDetail, summary="Get a site profile")
def get_site(session: DbSession, site_id: UUID) -> SiteDetail:
    """Return the full evidence-backed profile for one site."""
    site = _get_site_or_404(session, site_id)

    links = session.scalars(select(SiteParcelLink).where(SiteParcelLink.site_id == site.id)).all()
    parcels = []
    organization_ids: set[UUID] = set()
    for link in links:
        parcel = session.get(Parcel, link.parcel_id)
        if parcel is None:  # pragma: no cover - FK guarantees this
            continue
        parcels.append(serialize_parcel(parcel, link))
        if parcel.owner_organization_id:
            organization_ids.add(parcel.owner_organization_id)

    organizations = (
        [
            serialize_organization(org)
            for org in session.scalars(
                select(Organization).where(Organization.id.in_(organization_ids))
            ).all()
        ]
        if organization_ids
        else []
    )

    dependencies = [
        serialize_dependency(session, d)
        for d in session.scalars(
            select(InfrastructureDependency)
            .where(InfrastructureDependency.site_id == site.id)
            .order_by(InfrastructureDependency.distance_meters)
        ).all()
    ]

    estimates = [
        serialize_estimate(e)
        for e in session.scalars(select(SiteEstimate).where(SiteEstimate.site_id == site.id)).all()
    ]

    latest = session.scalars(
        select(Prediction)
        .where(Prediction.site_id == site.id, Prediction.is_backtest.is_(False))
        .order_by(Prediction.calculated_at.desc())
        .limit(1)
    ).first()

    history = session.scalars(
        select(SiteStageHistory)
        .where(SiteStageHistory.site_id == site.id)
        .order_by(SiteStageHistory.effective_date)
    ).all()

    summary = serialize_site_summary(site, parcel_count=len(parcels))
    return SiteDetail(
        **summary.model_dump(),
        summary=site.summary,
        boundary=geometry_to_geojson(site.boundary),
        parcels=parcels,
        organizations=organizations,
        dependencies=dependencies,
        estimates=estimates,
        latest_prediction=serialize_prediction(session, latest) if latest else None,
        stage_history=[serialize_stage_transition(h) for h in history],
        attributions=collect_attributions(session, site.id),
    )


@router.get(
    "/{site_id}/timeline",
    response_model=TimelineResponse,
    summary="Get a site's chronological narrative",
)
def get_timeline(session: DbSession, site_id: UUID) -> TimelineResponse:
    """Return evidence and stage transitions interleaved in date order.

    The timeline is the product's central artefact: it is what lets a reader see
    that land was assembled before permits were filed before construction began.
    """
    site = _get_site_or_404(session, site_id)

    entries: list[TimelineEntry] = []

    for record in session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.site_id == site.id)
        .order_by(EvidenceRecord.observed_at)
    ).all():
        evidence = serialize_evidence(session, record)
        entries.append(
            TimelineEntry(
                entry_type="evidence",
                occurred_on=record.observed_at,
                title=record.evidence_kind.replace("_", " ").capitalize(),
                detail=record.summary,
                evidence=evidence,
            )
        )

    for history in session.scalars(
        select(SiteStageHistory)
        .where(SiteStageHistory.site_id == site.id)
        .order_by(SiteStageHistory.effective_date)
    ).all():
        transition = serialize_stage_transition(history)
        entries.append(
            TimelineEntry(
                entry_type="stage_transition",
                occurred_on=history.effective_date,
                title=(
                    f"Stage {'downgraded' if history.is_downgrade else 'advanced'} to "
                    f"{DevelopmentStage(history.to_stage).label}"
                ),
                detail=history.rationale,
                stage_transition=transition,
            )
        )

    entries.sort(key=lambda e: (e.occurred_on, e.entry_type))

    return TimelineResponse(
        site_id=site.id,
        project_code=site.project_code,
        entries=entries,
        first_signal_date=site.first_signal_date,
        latest_signal_date=site.latest_signal_date,
    )


@router.get(
    "/{site_id}/evidence",
    response_model=EvidenceListResponse,
    summary="List a site's evidence records",
)
def get_evidence(
    session: DbSession,
    site_id: UUID,
    page: PageParams,
    kind: Annotated[str | None, Query(description="Filter by evidence kind")] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
) -> EvidenceListResponse:
    """Return a site's evidence with full provenance on every record."""
    site = _get_site_or_404(session, site_id)

    statement = select(EvidenceRecord).where(EvidenceRecord.site_id == site.id)
    if kind:
        statement = statement.where(EvidenceRecord.evidence_kind == kind)
    if min_confidence is not None:
        statement = statement.where(EvidenceRecord.confidence >= min_confidence)

    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    records = session.scalars(
        statement.order_by(EvidenceRecord.observed_at.desc()).limit(page.limit).offset(page.offset)
    ).all()

    return EvidenceListResponse(
        items=[serialize_evidence(session, r) for r in records],
        meta=PageMeta(
            total=total,
            limit=page.limit,
            offset=page.offset,
            has_more=page.offset + len(records) < total,
        ),
    )


@router.get(
    "/{site_id}/dependencies",
    response_model=list[DependencyResponse],
    summary="List a site's infrastructure dependencies",
)
def get_dependencies(session: DbSession, site_id: UUID) -> list[DependencyResponse]:
    """Return infrastructure a site depends on, nearest first."""
    site = _get_site_or_404(session, site_id)
    return [
        serialize_dependency(session, d)
        for d in session.scalars(
            select(InfrastructureDependency)
            .where(InfrastructureDependency.site_id == site.id)
            .order_by(InfrastructureDependency.distance_meters)
        ).all()
    ]


@router.get(
    "/{site_id}/score-history",
    response_model=ScoreHistoryResponse,
    summary="Show how a site's confidence changed over time",
)
def get_score_history(
    session: DbSession,
    site_id: UUID,
    include_backtests: Annotated[bool, Query()] = False,
) -> ScoreHistoryResponse:
    """Return every prediction recorded for a site, oldest first."""
    site = _get_site_or_404(session, site_id)

    statement = select(Prediction).where(Prediction.site_id == site.id)
    if not include_backtests:
        statement = statement.where(Prediction.is_backtest.is_(False))

    predictions = session.scalars(statement.order_by(Prediction.calculated_at)).all()
    return ScoreHistoryResponse(
        site_id=site.id,
        project_code=site.project_code,
        predictions=[serialize_prediction(session, p) for p in predictions],
    )


__all__ = ["router"]
