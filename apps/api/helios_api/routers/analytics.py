"""Regional analytics and data-quality measurement."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from helios_api.deps import DbSession
from helios_api.schemas import (
    AnalyticsStagesResponse,
    AreaConsumptionResponse,
    AreaTotalResponse,
    DetectionLagEntry,
    DetectionLagResponse,
    HeliosShareResponse,
    ProvenanceCompletenessResponse,
    StageDistributionEntry,
    StageGrowthPoint,
    StageGrowthResponse,
)
from helios_domain.models import (
    AreaTotal,
    EvidenceRecord,
    Site,
    SiteEstimate,
    SiteStageHistory,
    Source,
)
from helios_domain.ontology import DevelopmentStage
from helios_domain.regions import DEFAULT_REGION_SLUG, Region, UnknownRegionError, get_region
from helios_scoring.impact import annualise_power_mwh

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


GALLONS_PER_MILLION = 1_000_000

PUBLIC_SUPPLY = "public_supply_water_withdrawal"
ELECTRICITY_SALES = "electricity_retail_sales"

_GRANULARITY_NOTE = (
    "Water is published per county and electricity per state, because no public "
    "source breaks retail electricity sales to county nationally. A state total "
    "is a much weaker denominator for a metro-scale region, and the two are not "
    "comparable to each other. Each figure carries the area it actually covers."
)

_CAVEAT = (
    "A ratio of an inference to a measurement is weaker than either. The area "
    "total is reported and whole-area, covering every existing user; the Helios "
    "figure is inferred from acreage for sites that in most cases are not built. "
    "This is a sense of scale, not a forecast of what the area will consume."
)


@router.get(
    "/area-consumption",
    response_model=AreaConsumptionResponse,
    summary="What the region already consumes, measured",
)
def area_consumption(
    session: DbSession,
    region: Annotated[str | None, Query(description="Region slug")] = None,
) -> AreaConsumptionResponse:
    """Return published water and electricity totals for the region.

    Helios's per-site power and water figures are inferences from acreage, and on
    their own they have no scale: 40 MW is either negligible or alarming
    depending on what the surrounding area already draws. These totals are the
    denominator, and unlike everything Helios derives, an agency measured them.

    The reported totals and the inferred comparisons are returned as separate
    lists. Merging them would be the exact error this project exists to avoid.
    """
    slug = region or DEFAULT_REGION_SLUG
    try:
        resolved = get_region(slug)
    except UnknownRegionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    rows = session.execute(
        select(AreaTotal, Source)
        .join(Source, Source.id == AreaTotal.source_id)
        .where(
            or_(
                and_(
                    AreaTotal.area_kind == "county",
                    AreaTotal.area_code.in_(resolved.county_fips),
                ),
                and_(
                    AreaTotal.area_kind == "state",
                    AreaTotal.area_code == resolved.state_code,
                ),
            )
        )
        .order_by(
            AreaTotal.area_kind,
            AreaTotal.area_name,
            AreaTotal.metric,
            AreaTotal.sector,
        )
    ).all()

    totals = [
        AreaTotalResponse(
            area_kind=row.area_kind,
            area_code=row.area_code,
            area_name=row.area_name,
            metric=row.metric,
            sector=row.sector,
            value=row.value,
            unit=row.unit,
            reference_year=row.reference_year,
            assertion_class=row.assertion_class,
            source_slug=source.slug,
            source_name=source.name,
        )
        for row, source in rows
    ]

    comparisons = _build_comparisons(session, resolved, [row for row, _ in rows])

    return AreaConsumptionResponse(
        region_slug=resolved.slug,
        region_name=resolved.name,
        totals=totals,
        comparisons=comparisons,
        granularity_note=_GRANULARITY_NOTE,
        note=(
            "Every figure in `totals` is reported: an agency measured and published "
            "it. Every figure in `comparisons` is inferred, and inherits the "
            "assumptions behind Helios's acreage-based estimates."
        ),
    )


def _latest_sum(rows: list[AreaTotal], metric: str, sector: str = "all") -> tuple[float, int]:
    """Sum one metric across the region's areas, within a single reference year.

    Summing across years would silently mix a 2015 county with a 2020 one, so
    only the most recent year present is used and it is returned alongside the
    figure rather than dropped.

    Args:
        rows: Area totals already scoped to the region.
        metric: Metric name to sum.
        sector: Reporting sector, ``all`` where the publisher gives no breakdown.

    Returns:
        ``(total, reference_year)``, or ``(0.0, 0)`` when the metric is absent.
    """
    matching = [r for r in rows if r.metric == metric and r.sector == sector]
    if not matching:
        return 0.0, 0
    year = max(r.reference_year for r in matching)
    return sum(r.value for r in matching if r.reference_year == year), year


def _site_estimate_totals(
    session: Session, region_slug: str
) -> dict[str, tuple[float, float, float, int]]:
    """Sum each estimate type across the region's sites.

    Bounds are summed independently, which widens the band rather than narrowing
    it. That is the honest direction: the low case is every site landing at its
    low end, and nothing in the records says which way any individual site goes.

    The sums are rounded to one decimal because float addition is not
    associative and Postgres does not promise a row order, so the same 13 sites
    summed twice can differ in the last bit. Every input is already produced
    rounded to one decimal by ``helios_scoring.impact``, so nothing real is lost
    -- but without this the static export is not byte-reproducible, and a
    published figure that changes when nothing changed is a defect in a project
    whose whole claim is that its numbers can be re-derived.
    """
    statement = (
        select(
            SiteEstimate.estimate_type,
            func.sum(SiteEstimate.lower_value),
            func.sum(SiteEstimate.likely_value),
            func.sum(SiteEstimate.upper_value),
            func.count(func.distinct(SiteEstimate.site_id)),
        )
        .join(Site, Site.id == SiteEstimate.site_id)
        .where(Site.region_slug == region_slug)
        .group_by(SiteEstimate.estimate_type)
    )
    return {
        estimate_type: (
            round(float(lower or 0), 1),
            round(float(likely or 0), 1),
            round(float(upper or 0), 1),
            int(sites),
        )
        for estimate_type, lower, likely, upper, sites in session.execute(statement).all()
    }


def _share(part: float, whole: float) -> float | None:
    """Percentage of ``whole`` that ``part`` represents, or None if undefined."""
    if whole <= 0:
        return None
    return round(part / whole * 100, 2)


def _build_comparisons(
    session: Session, region: Region, rows: list[AreaTotal]
) -> list[HeliosShareResponse]:
    """Set the region's inferred site demand beside its reported area totals."""
    estimates = _site_estimate_totals(session, region.slug)
    comparisons: list[HeliosShareResponse] = []

    county_names = ", ".join(sorted({r.area_name for r in rows if r.area_kind == "county"}))

    public_supply, water_year = _latest_sum(rows, PUBLIC_SUPPLY)
    water = estimates.get("water_usage")
    if public_supply > 0 and water is not None:
        lower, likely, upper, sites = water
        # Site estimates are gallons per day; the county totals are millions of
        # gallons per day. Comparing them unconverted would be off by a million.
        band = tuple(v / GALLONS_PER_MILLION for v in (lower, likely, upper))
        comparisons.append(
            HeliosShareResponse(
                metric=PUBLIC_SUPPLY,
                unit="Mgal/d",
                area_kind="county",
                area_name=county_names or region.name,
                area_value=round(public_supply, 2),
                area_reference_year=water_year,
                sites_counted=sites,
                inferred_lower=round(band[0], 4),
                inferred_likely=round(band[1], 4),
                inferred_upper=round(band[2], 4),
                share_lower_pct=_share(band[0], public_supply),
                share_likely_pct=_share(band[1], public_supply),
                share_upper_pct=_share(band[2], public_supply),
                method="Summed site water estimates against reported public-supply withdrawal",
                assumptions={
                    "gallons_per_million": GALLONS_PER_MILLION,
                    "note": (
                        "Public supply is the municipal water a data centre on the "
                        "city system competes for. Agricultural and thermoelectric "
                        "withdrawals are reported separately and are not in this "
                        "denominator."
                    ),
                },
                caveat=_CAVEAT,
            )
        )

    sales, power_year = _latest_sum(rows, ELECTRICITY_SALES, sector="total")
    power = estimates.get("power_capacity")
    if sales > 0 and power is not None:
        lower, likely, upper, sites = power
        annual = annualise_power_mwh(lower, likely, upper)
        if annual is not None:
            comparisons.append(
                HeliosShareResponse(
                    metric=ELECTRICITY_SALES,
                    unit="MWh/yr",
                    area_kind="state",
                    area_name=region.state_code,
                    area_value=round(sales, 1),
                    area_reference_year=power_year,
                    sites_counted=sites,
                    inferred_lower=annual.lower,
                    inferred_likely=annual.likely,
                    inferred_upper=annual.upper,
                    share_lower_pct=_share(annual.lower, sales),
                    share_likely_pct=_share(annual.likely, sales),
                    share_upper_pct=_share(annual.upper, sales),
                    method=annual.method,
                    assumptions=annual.assumptions,
                    caveat=(
                        f"{_CAVEAT} The denominator is statewide while the sites are "
                        f"in {region.name}, so this understates the local share."
                    ),
                )
            )

    return comparisons


__all__ = ["router"]
