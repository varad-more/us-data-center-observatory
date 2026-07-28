"""Regional analytics and data-quality measurement."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from helios_api.deps import DbSession
from helios_api.schemas import (
    AnalyticsStagesResponse,
    DetectionLagEntry,
    DetectionLagResponse,
    ProvenanceCompletenessResponse,
    StageDistributionEntry,
    StageGrowthPoint,
    StageGrowthResponse,
)
from helios_domain.models import EvidenceRecord, Site, SiteStageHistory
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
    "/growth",
    response_model=StageGrowthResponse,
    summary="Development activity over time",
)
def stage_growth(
    session: DbSession,
    region: Annotated[str | None, Query(description="Region slug filter")] = None,
) -> StageGrowthResponse:
    """Return, month by month, how many sites had reached each stage.

    Built from ``site_stage_history``, which is append-only, so this is a replay
    of what the records showed rather than a snapshot of today projected
    backwards.

    The series is cumulative and monotonic by construction: a site that reached
    stage 6 has necessarily passed stage 4, so it is counted in both. Counting
    only a site's *current* stage would make the earlier stages appear to empty
    out as projects progressed, which reads as decline rather than as movement.

    Downgrades are deliberately not subtracted. The question this answers is
    "what had the record shown by this date", and a stage that was later
    retracted was still shown at the time.
    """
    statement = select(
        SiteStageHistory.effective_date,
        SiteStageHistory.to_stage,
        SiteStageHistory.site_id,
    ).join(Site, Site.id == SiteStageHistory.site_id)
    if region:
        statement = statement.where(Site.region_slug == region)

    rows = session.execute(statement.order_by(SiteStageHistory.effective_date)).all()

    if not rows:
        return StageGrowthResponse(
            region_slug=region,
            points=[],
            note="No stage transitions recorded.",
        )

    # Highest stage each site had reached, replayed forward month by month.
    highest_by_site: dict[Any, int] = {}
    by_month: dict[str, list[tuple[Any, int]]] = defaultdict(list)
    for effective_date, to_stage, site_id in rows:
        by_month[effective_date.strftime("%Y-%m")].append((site_id, int(to_stage)))

    points: list[StageGrowthPoint] = []
    for month in sorted(by_month):
        for site_id, to_stage in by_month[month]:
            highest_by_site[site_id] = max(highest_by_site.get(site_id, 0), to_stage)

        cumulative = {
            int(stage): sum(1 for reached in highest_by_site.values() if reached >= int(stage))
            for stage in DevelopmentStage
        }
        points.append(
            StageGrowthPoint(
                month=month,
                cumulative_by_stage=cumulative,
                sites_tracked=len(highest_by_site),
            )
        )

    return StageGrowthResponse(
        region_slug=region,
        points=points,
        note=(
            "Cumulative: a site is counted at every stage it has reached, not only "
            "its current one. Dated by the evidence the transition rests on, not by "
            "when Helios ingested it."
        ),
    )


@router.get(
    "/detection-lag",
    response_model=DetectionLagResponse,
    summary="How long Helios took to notice each stage change",
)
def detection_lag(
    session: DbSession,
    region: Annotated[str | None, Query(description="Region slug filter")] = None,
) -> DetectionLagResponse:
    """Measure the gap between when a transition happened and when Helios saw it.

    Helios is described as early-warning infrastructure. That is a testable
    claim, and this endpoint is the test: the distance between
    ``effective_date`` - the date the underlying record supports - and
    ``detected_at``, when the pipeline recorded it.

    Negative lag is real and is reported rather than clamped. It means Helios
    recorded a transition before the effective date it later attributed to it,
    which happens when a subsequent document moves the effective date earlier.
    Clamping at zero would quietly flatter the system.
    """
    statement = (
        select(
            Site.project_code,
            SiteStageHistory.to_stage,
            SiteStageHistory.effective_date,
            SiteStageHistory.detected_at,
        )
        .join(Site, Site.id == SiteStageHistory.site_id)
        .where(SiteStageHistory.effective_date.isnot(None))
    )
    if region:
        statement = statement.where(Site.region_slug == region)

    entries: list[DetectionLagEntry] = []
    for project_code, to_stage, effective_date, detected_at in session.execute(statement).all():
        lag = (detected_at.date() - effective_date).days
        entries.append(
            DetectionLagEntry(
                project_code=project_code,
                to_stage=int(to_stage),
                stage_label=DevelopmentStage(int(to_stage)).label,
                effective_date=effective_date,
                detected_at=detected_at,
                lag_days=lag,
            )
        )

    if not entries:
        return DetectionLagResponse(
            region_slug=region,
            transitions=0,
            median_lag_days=None,
            p90_lag_days=None,
            min_lag_days=None,
            max_lag_days=None,
            slowest=[],
            note="No dated stage transitions recorded.",
        )

    lags = sorted(entry.lag_days for entry in entries)
    entries.sort(key=lambda e: e.lag_days, reverse=True)

    return DetectionLagResponse(
        region_slug=region,
        transitions=len(entries),
        median_lag_days=_percentile(lags, 0.5),
        p90_lag_days=_percentile(lags, 0.9),
        min_lag_days=lags[0],
        max_lag_days=lags[-1],
        slowest=entries[:10],
        note=(
            "Lag is detection date minus the evidence date the transition rests on. "
            "On a fixture-seeded deployment every record was ingested at once, so "
            "these figures describe the recorded corpus, not live operation."
        ),
    )


def _percentile(sorted_values: list[int], fraction: float) -> float:
    """Linear-interpolated percentile over a pre-sorted list."""
    if not sorted_values:
        raise ValueError("percentile of an empty sequence")
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = fraction * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return round(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight, 1)


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
