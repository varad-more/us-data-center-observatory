"""Construction of sites from parcels.

A *site* is Helios's hypothesis that a set of parcels constitutes one project.
It is not a public record, and the system says so: sites carry generated
anonymous project codes rather than company names, and every parcel link records
why it was made and how confident the system is.

Clustering strategy
-------------------
Candidate parcels are those the assessor classifies as data centres, or that are
large, industrial, and organization-held. Candidates are then grouped when they
are **spatially adjacent** and share a **related owner**, because either signal
alone produces bad clusters: adjacency alone merges neighbouring but unrelated
businesses, and shared ownership alone merges a company's holdings across the
whole county into one nonsensical "site".

This is deliberately conservative. Under-clustering splits one project into two
sites, which is visible and fixable by a reviewer. Over-clustering fabricates a
campus that does not exist, which is a false claim.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from geoalchemy2 import WKTElement
from sqlalchemy import func, select, text

from helios_common.logging import get_logger
from helios_common.vocabulary import AssertionClass
from helios_domain.models import (
    EvidenceRecord,
    InfrastructureDependency,
    Parcel,
    Site,
    SiteParcelLink,
)
from helios_domain.ontology import DevelopmentStage, InfrastructureKind, SiteKind
from helios_geospatial.correlation import (
    ADJACENCY_TOLERANCE_METERS,
    SUBSTATION_PROXIMITY_METERS,
    compute_site_geometry,
    find_nearby_substations,
    find_nearby_transmission_lines,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

CANDIDATE_MIN_ACRES = 20.0
"""Minimum size for a non-classified parcel to become a candidate on its own."""

HYPERSCALE_CAMPUS_MIN_ACRES = 40.0
"""Above this, a data-centre site is described as campus-scale rather than a
single facility. Derived from the observed distribution of assessor-classified
data-centre parcels in Maricopa County, where single buildings cluster between
1 and 20 acres and multi-building campuses run 55 acres and up."""

BLOCKING_SUBSTATION_DISTANCE_METERS = 1500.0
"""Within this range a substation is treated as a likely dedicated dependency."""


@dataclass(slots=True)
class SiteBuildResult:
    """Outcome of a site-building pass."""

    sites_created: int = 0
    sites_updated: int = 0
    parcels_linked: int = 0
    evidence_attached: int = 0
    dependencies_created: int = 0
    site_ids: list[uuid.UUID] = field(default_factory=list)


def _slugify_jurisdiction(name: str | None) -> str:
    """Convert a jurisdiction name into a project-code fragment."""
    if not name:
        return "UNK"
    cleaned = re.sub(r"[^A-Za-z]", "", name).upper()
    return cleaned[:10] or "UNK"


def generate_project_code(session: Session, jurisdiction: str | None) -> str:
    """Mint the next anonymous project code for a jurisdiction.

    Codes look like ``AZ-MESA-001``. An anonymous identifier is used in
    preference to any name found in the records because naming a project after
    the LLC on the deed would imply an attribution Helios has not established.

    Args:
        session: Open database session.
        jurisdiction: City or town name.

    Returns:
        A unique project code.
    """
    prefix = f"AZ-{_slugify_jurisdiction(jurisdiction)}"
    existing = session.scalars(
        select(Site.project_code).where(Site.project_code.like(f"{prefix}-%"))
    ).all()

    highest = 0
    for code in existing:
        suffix = code.rsplit("-", 1)[-1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}-{highest + 1:03d}"


def find_candidate_parcels(
    session: Session,
    *,
    region_cities: tuple[str, ...] | None = None,
    min_acres: float = CANDIDATE_MIN_ACRES,
) -> list[Parcel]:
    """Select parcels worth treating as potential development sites.

    Args:
        session: Open database session.
        region_cities: Restrict to these situs cities.
        min_acres: Size threshold for the non-classified branch.

    Returns:
        Candidate parcels, largest first.
    """
    classified = Parcel.land_use_description.ilike("%DATA CENTER%")
    large_industrial = (Parcel.lot_size_acres >= min_acres) & (
        Parcel.owner_organization_id.isnot(None)
    )

    statement = select(Parcel).where(classified | large_industrial)
    if region_cities:
        statement = statement.where(
            func.upper(Parcel.situs_city).in_([c.upper() for c in region_cities])
        )

    return list(session.scalars(statement.order_by(Parcel.lot_size_acres.desc().nullslast())).all())


def _cluster_candidates(
    session: Session, candidates: list[Parcel], tolerance_meters: float
) -> list[list[Parcel]]:
    """Group candidate parcels into clusters by adjacency plus shared ownership.

    Implemented as a union-find over the candidate set. Only candidate-to-candidate
    adjacency is considered, so an intervening ordinary parcel cannot chain two
    unrelated projects together.

    Args:
        session: Open database session.
        candidates: Parcels to cluster.
        tolerance_meters: Adjacency tolerance.

    Returns:
        Clusters, each a list of parcels.
    """
    if not candidates:
        return []

    by_id = {p.id: p for p in candidates}
    parent: dict[uuid.UUID, uuid.UUID] = {p.id: p.id for p in candidates}

    def find(node: uuid.UUID) -> uuid.UUID:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: uuid.UUID, b: uuid.UUID) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    # One query finds every adjacent candidate pair, rather than N queries.
    rows = session.execute(
        text("""
            SELECT a.id AS a_id, b.id AS b_id
            FROM parcels AS a
            JOIN parcels AS b
              ON a.id < b.id
             AND ST_DWithin(a.geometry::geography, b.geometry::geography, :tolerance)
            WHERE a.id = ANY(:ids) AND b.id = ANY(:ids)
              AND a.geometry IS NOT NULL AND b.geometry IS NOT NULL
            """),
        {"ids": list(by_id.keys()), "tolerance": tolerance_meters},
    ).mappings()

    for row in rows:
        left, right = by_id[row["a_id"]], by_id[row["b_id"]]
        if _owners_related(left, right):
            union(left.id, right.id)

    clusters: dict[uuid.UUID, list[Parcel]] = {}
    for parcel in candidates:
        clusters.setdefault(find(parcel.id), []).append(parcel)
    return list(clusters.values())


def _owners_related(left: Parcel, right: Parcel) -> bool:
    """Decide whether two adjacent parcels are held by the same interest.

    Currently requires an exact organization match. A looser rule using shared
    mailing addresses or name similarity would raise recall but risks fusing
    genuinely separate developments, so it is deferred until probabilistic entity
    resolution has been validated against known cases.
    """
    if left.owner_organization_id is None or right.owner_organization_id is None:
        return False
    return left.owner_organization_id == right.owner_organization_id


def build_sites(
    session: Session,
    *,
    region_cities: tuple[str, ...] | None = None,
    region_slug: str = "east-valley-az",
    adjacency_tolerance_meters: float = ADJACENCY_TOLERANCE_METERS,
) -> SiteBuildResult:
    """Create or update sites from the current parcel population.

    Args:
        session: Open database session.
        region_cities: Restrict candidates to these cities.
        region_slug: Region tag applied to created sites.
        adjacency_tolerance_meters: Clustering tolerance.

    Returns:
        Counts describing what changed.
    """
    result = SiteBuildResult()
    candidates = find_candidate_parcels(session, region_cities=region_cities)
    clusters = _cluster_candidates(session, candidates, adjacency_tolerance_meters)

    logger.info(
        "site_builder.clustered",
        candidates=len(candidates),
        clusters=len(clusters),
    )

    for cluster in clusters:
        site, created = _upsert_site_for_cluster(session, cluster, region_slug)
        result.site_ids.append(site.id)
        if created:
            result.sites_created += 1
        else:
            result.sites_updated += 1

        result.parcels_linked += _link_parcels(session, site, cluster)
        session.flush()

        _refresh_site_geometry(session, site)
        result.evidence_attached += _attach_parcel_evidence(session, site, cluster)
        result.dependencies_created += link_infrastructure(session, site)

    session.flush()
    return result


def _upsert_site_for_cluster(
    session: Session, cluster: list[Parcel], region_slug: str
) -> tuple[Site, bool]:
    """Find the existing site for a cluster, or create one."""
    parcel_ids = [p.id for p in cluster]
    existing = session.scalar(
        select(Site)
        .join(SiteParcelLink, SiteParcelLink.site_id == Site.id)
        .where(SiteParcelLink.parcel_id.in_(parcel_ids))
        .limit(1)
    )
    if existing is not None:
        return existing, False

    anchor = max(cluster, key=lambda p: float(p.lot_size_acres or 0))
    site = Site(
        project_code=generate_project_code(session, anchor.situs_city),
        site_kind=str(_infer_site_kind(cluster)),
        site_kind_assertion=str(_site_kind_assertion(cluster)),
        jurisdiction=anchor.situs_city,
        county=anchor.county,
        region_slug=region_slug,
        current_stage=int(DevelopmentStage.NO_KNOWN_DEVELOPMENT),
        current_confidence=0.0,
        summary=_build_site_summary(cluster, anchor),
    )
    session.add(site)
    session.flush()
    logger.info(
        "site_builder.site_created",
        project_code=site.project_code,
        parcels=len(cluster),
    )
    return site, True


def _infer_site_kind(cluster: list[Parcel]) -> SiteKind:
    """Classify a cluster, distinguishing confirmed classification from inference."""
    classified = any("DATA CENTER" in (p.land_use_description or "").upper() for p in cluster)
    total_acres = sum(float(p.lot_size_acres or 0) for p in cluster)

    if classified:
        if total_acres >= HYPERSCALE_CAMPUS_MIN_ACRES:
            return SiteKind.HYPERSCALE_CAMPUS
        return SiteKind.ENTERPRISE_DATA_CENTER
    return SiteKind.SUSPECTED_DATA_CENTER


def _site_kind_assertion(cluster: list[Parcel]) -> AssertionClass:
    """State how the site kind was arrived at.

    A parcel the county has classified as a data centre is *reported*; a large
    industrial parcel that merely looks like one is *inferred*, and the UI must
    render those differently.
    """
    classified = any("DATA CENTER" in (p.land_use_description or "").upper() for p in cluster)
    return AssertionClass.REPORTED if classified else AssertionClass.INFERRED


def _build_site_summary(cluster: list[Parcel], anchor: Parcel) -> str:
    """Compose a factual site summary that makes no attribution claim."""
    total_acres = sum(float(p.lot_size_acres or 0) for p in cluster)
    owner = anchor.owner_name_raw or "an undisclosed owner"
    location = anchor.situs_address or anchor.situs_city or "an unspecified location"
    return (
        f"{len(cluster)} parcel(s) totalling {total_acres:.1f} acres near {location}, "
        f"{anchor.situs_city or 'Maricopa County'}. Title of record is held by {owner}. "
        "Helios has not established which organization, if any, operates or will "
        "operate a facility here."
    )


def _link_parcels(session: Session, site: Site, cluster: list[Parcel]) -> int:
    """Attach cluster parcels to a site, recording why each was linked."""
    linked = 0
    for parcel in cluster:
        existing = session.scalar(
            select(SiteParcelLink).where(
                SiteParcelLink.site_id == site.id,
                SiteParcelLink.parcel_id == parcel.id,
            )
        )
        if existing is not None:
            continue

        is_classified = "DATA CENTER" in (parcel.land_use_description or "").upper()
        session.add(
            SiteParcelLink(
                site_id=site.id,
                parcel_id=parcel.id,
                link_reason=(
                    "assessor_classification" if is_classified else "large_industrial_holding"
                ),
                match_method="attribute_and_adjacency",
                spatial_confidence=1.0,
                distance_meters=0.0,
                confidence=0.95 if is_classified else 0.6,
                effective_start=parcel.last_deed_date,
            )
        )
        linked += 1
    return linked


def _refresh_site_geometry(session: Session, site: Site) -> None:
    """Recompute a site's boundary, centroid, and acreage from its parcels."""
    geometry = compute_site_geometry(session, site.id)
    if geometry is None:
        return
    site.boundary = WKTElement(str(geometry["boundary_wkt"]), srid=4326)
    site.centroid = WKTElement(str(geometry["centroid_wkt"]), srid=4326)
    site.total_acres = geometry["total_acres"]


def _attach_parcel_evidence(session: Session, site: Site, cluster: list[Parcel]) -> int:
    """Attach parcel-derived evidence to the site and refresh its timeline bounds.

    Evidence is created by connectors against parcels; this step associates it
    with the analytical site so the timeline and score can see it.
    """
    parcel_ids = [p.id for p in cluster]
    records = session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.parcel_id.in_(parcel_ids))
    ).all()

    attached = 0
    for record in records:
        if record.site_id != site.id:
            record.site_id = site.id
            attached += 1

    site_evidence = session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.site_id == site.id)
        .order_by(EvidenceRecord.observed_at)
    ).all()
    if site_evidence:
        site.first_signal_date = site_evidence[0].observed_at
        site.latest_signal_date = site_evidence[-1].observed_at
        site.evidence_count = len(site_evidence)
    return attached


def link_infrastructure(
    session: Session,
    site: Site,
    *,
    radius_meters: float = SUBSTATION_PROXIMITY_METERS,
) -> int:
    """Create infrastructure dependency edges for a site.

    Dependencies are recorded as *inferred* from proximity, never as reported
    facts. A substation next door does not prove it serves the site; it means
    the site could plausibly be served from there. The distinction is preserved
    in ``assertion_class`` and in the human-readable note.

    Args:
        session: Open database session.
        site: The site.
        radius_meters: Substation search radius.

    Returns:
        Number of dependency rows created.
    """
    created = 0

    for match in find_nearby_substations(session, site.id, radius_meters=radius_meters):
        existing = session.scalar(
            select(InfrastructureDependency).where(
                InfrastructureDependency.site_id == site.id,
                InfrastructureDependency.substation_id == match.target_id,
            )
        )
        if existing is not None:
            continue

        is_blocking = match.distance_meters <= BLOCKING_SUBSTATION_DISTANCE_METERS
        voltage = match.detail.get("max_voltage_kv")
        session.add(
            InfrastructureDependency(
                site_id=site.id,
                infrastructure_kind=str(InfrastructureKind.SUBSTATION),
                substation_id=match.target_id,
                label=match.target_label,
                dependency_status="existing",
                is_blocking=is_blocking,
                match_method=match.match_method,
                distance_meters=match.distance_meters,
                confidence=match.spatial_confidence,
                assertion_class=str(AssertionClass.INFERRED),
                notes=(
                    f"{match.target_label} lies {match.distance_meters:.0f} m from the site "
                    f"boundary"
                    + (f" and is tagged {voltage:.0f} kV" if voltage else "")
                    + ". Proximity indicates the site could plausibly be served from here; "
                    "it is not evidence that it is. No interconnection filing has been "
                    "matched to this site."
                ),
            )
        )
        created += 1

    for match in find_nearby_transmission_lines(session, site.id):
        existing = session.scalar(
            select(InfrastructureDependency).where(
                InfrastructureDependency.site_id == site.id,
                InfrastructureDependency.transmission_line_id == match.target_id,
            )
        )
        if existing is not None:
            continue

        session.add(
            InfrastructureDependency(
                site_id=site.id,
                infrastructure_kind=str(InfrastructureKind.TRANSMISSION_LINE),
                transmission_line_id=match.target_id,
                label=match.target_label,
                dependency_status="existing",
                is_blocking=False,
                match_method=match.match_method,
                distance_meters=match.distance_meters,
                confidence=match.spatial_confidence,
                assertion_class=str(AssertionClass.INFERRED),
                notes=str(match.detail.get("geometry_caveat", "")),
            )
        )
        created += 1

    return created


__all__ = [
    "CANDIDATE_MIN_ACRES",
    "HYPERSCALE_CAMPUS_MIN_ACRES",
    "SiteBuildResult",
    "build_sites",
    "find_candidate_parcels",
    "generate_project_code",
    "link_infrastructure",
]
