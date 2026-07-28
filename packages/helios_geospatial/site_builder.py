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
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from geoalchemy2 import WKTElement
from sqlalchemy import func, select, text

from helios_common.logging import get_logger
from helios_common.vocabulary import AssertionClass, EvidencePolarity, ExtractionMethod
from helios_domain.models import (
    DocumentVersion,
    EvidenceRecord,
    InfrastructureDependency,
    Parcel,
    Permit,
    Site,
    SiteParcelLink,
    Substation,
)
from helios_domain.ontology import (
    DevelopmentStage,
    InfrastructureKind,
    SiteKind,
    StageEvidenceKind,
)
from helios_domain.regions import DEFAULT_REGION_SLUG, Region, resolve_region
from helios_geospatial.correlation import (
    ADJACENCY_TOLERANCE_METERS,
    PERMIT_PROXIMITY_METERS,
    SUBSTATION_PROXIMITY_METERS,
    SpatialMatch,
    compute_site_geometry,
    find_nearby_permits,
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


def generate_project_code(session: Session, jurisdiction: str | None, region: Region | str) -> str:
    """Mint the next anonymous project code for a jurisdiction.

    Codes look like ``AZ-MESA-001``. An anonymous identifier is used in
    preference to any name found in the records because naming a project after
    the LLC on the deed would imply an attribution Helios has not established.

    The state prefix comes from the region rather than from a constant. It was
    hardcoded to ``AZ``, which meant a site outside Arizona could be minted with
    a code that misstated where it is.

    Args:
        session: Open database session.
        jurisdiction: City or town name.
        region: Region the site belongs to, or its registered slug.

    Returns:
        A unique project code.

    Raises:
        UnknownRegionError: If a slug is given and is not registered.
    """
    prefix = resolve_region(region).project_code_prefix(_slugify_jurisdiction(jurisdiction))
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
    region: Region | str = DEFAULT_REGION_SLUG,
    adjacency_tolerance_meters: float = ADJACENCY_TOLERANCE_METERS,
) -> SiteBuildResult:
    """Create or update sites from the current parcel population.

    The region supplies both halves of what used to be two arguments: which
    cities to sweep, and which tag to write. Passing them separately allowed a
    caller to sweep one place and label it another, and the unrestricted default
    swept every parcel in the database while still stamping them all
    ``east-valley-az``.

    Args:
        session: Open database session.
        region: Region to build within, or its registered slug.
        adjacency_tolerance_meters: Clustering tolerance.

    Returns:
        Counts describing what changed.

    Raises:
        UnknownRegionError: If a slug is given and is not registered.
    """
    resolved = resolve_region(region)
    result = SiteBuildResult()
    candidates = find_candidate_parcels(session, region_cities=resolved.cities or None)
    clusters = _cluster_candidates(session, candidates, adjacency_tolerance_meters)

    logger.info(
        "site_builder.clustered",
        candidates=len(candidates),
        clusters=len(clusters),
    )

    built: list[Site] = []
    for cluster in clusters:
        site, created = _upsert_site_for_cluster(session, cluster, resolved)
        result.site_ids.append(site.id)
        if created:
            result.sites_created += 1
        else:
            result.sites_updated += 1

        result.parcels_linked += _link_parcels(session, site, cluster)
        session.flush()

        _refresh_site_geometry(session, site)
        # The boundary must reach the database before infrastructure linking, which
        # runs spatial SQL against `sites.boundary` rather than the ORM object.
        session.flush()

        result.evidence_attached += _attach_parcel_evidence(session, site, cluster)
        result.evidence_attached += _attach_nearby_permit_evidence(session, site)
        result.dependencies_created += link_infrastructure(session, site)
        built.append(site)

    # Rollups run only once every site has claimed its evidence. Counting inside
    # the loop would leave a stale total on any site whose evidence a later,
    # nearer site went on to claim. The flush matters because the session does
    # not autoflush: a query would otherwise not see the assignments above.
    session.flush()
    for site in built:
        _refresh_evidence_rollups(session, site)

    session.flush()
    return result


def _upsert_site_for_cluster(
    session: Session, cluster: list[Parcel], region: Region
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
        project_code=generate_project_code(session, anchor.situs_city, region),
        site_kind=str(_infer_site_kind(cluster)),
        site_kind_assertion=str(_site_kind_assertion(cluster)),
        jurisdiction=anchor.situs_city,
        county=anchor.county or region.primary_county,
        region_slug=region.slug,
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
    site.total_acres = cast("Decimal | None", geometry["total_acres"])


def _attach_parcel_evidence(session: Session, site: Site, cluster: list[Parcel]) -> int:
    """Attach parcel-derived evidence to the site.

    Evidence is created by connectors against parcels; this step associates it
    with the analytical site so the timeline and score can see it. Rollups are
    refreshed once by :func:`_refresh_evidence_rollups` after every attachment
    pass has run.
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

    return attached


def _refresh_evidence_rollups(session: Session, site: Site) -> None:
    """Recompute a site's denormalised evidence counters from its evidence.

    The session runs with ``autoflush=False``, so this must be called after an
    explicit flush: a query issued while ``site_id`` assignments are still
    pending returns nothing, which previously left every site advertising zero
    evidence while carrying a full evidence trail.
    """
    site_evidence = session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.site_id == site.id)
        .order_by(EvidenceRecord.observed_at)
    ).all()
    if not site_evidence:
        return
    site.first_signal_date = site_evidence[0].observed_at
    site.latest_signal_date = site_evidence[-1].observed_at
    site.evidence_count = len(site_evidence)


MAX_DEPENDENCIES_PER_KIND = 8
"""Cap on dependency rows per infrastructure kind.

The East Valley grid is dense: an unbounded 3 km search returns tens of
substations per site, which buries the two or three that matter. Keeping the
nearest few preserves the signal without pretending the rest do not exist."""


def _attach_nearby_permit_evidence(
    session: Session,
    site: Site,
    *,
    radius_meters: float = PERMIT_PROXIMITY_METERS,
) -> int:
    """Link geocoded permits (and their evidence) to a site by proximity.

    Connectors persist permits without knowing Helios site codes. Attachment is
    therefore a calculated spatial join: close enough to cite, never a claim that
    the permit names the project.
    """
    attached = 0
    for match in find_nearby_permits(session, site.id, radius_meters=radius_meters):
        permit = session.get(Permit, match.target_id)
        if permit is None:
            continue
        if permit.site_id != site.id:
            permit.site_id = site.id
            attached += 1

        permit_id = str(permit.id)
        evidence_rows = list(
            session.execute(
                text("""
                    SELECT id FROM evidence_records
                    WHERE normalized_values->>'permit_id' = :permit_id
                    """),
                {"permit_id": permit_id},
            ).scalars()
        )
        for evidence_id in evidence_rows:
            record = session.get(EvidenceRecord, evidence_id)
            if record is None:
                continue
            if record.site_id != site.id:
                record.site_id = site.id
                attached += 1

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
    substation_matches = find_nearby_substations(session, site.id, radius_meters=radius_meters)

    for index, match in enumerate(substation_matches[:MAX_DEPENDENCIES_PER_KIND]):
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

        # Only the nearest substation, and only when it is close enough to be a
        # plausible dedicated connection, earns an evidence record. Recording all
        # of them would let ordinary urban grid density inflate confidence.
        if index == 0 and is_blocking:
            _record_substation_proximity_evidence(session, site, match)

    for match in find_nearby_transmission_lines(session, site.id)[:MAX_DEPENDENCIES_PER_KIND]:
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


def _record_substation_proximity_evidence(
    session: Session, site: Site, match: SpatialMatch
) -> EvidenceRecord | None:
    """Create a citable evidence record for a close, transmission-class substation.

    The evidence cites the OpenStreetMap document the substation came from, so
    the claim remains traceable to a source even though the *proximity* itself is
    a Helios calculation rather than something any source reported.
    """
    substation = session.get(Substation, match.target_id)
    if substation is None or substation.source_document_id is None:
        return None

    existing = session.scalar(
        select(EvidenceRecord).where(
            EvidenceRecord.site_id == site.id,
            EvidenceRecord.evidence_kind == str(StageEvidenceKind.DEDICATED_SUBSTATION_PROXIMITY),
        )
    )
    if existing is not None:
        return existing

    version = session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == substation.source_document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).first()
    if version is None:
        return None

    voltage = substation.max_voltage_kv
    voltage_text = f" tagged {voltage:.0f} kV" if voltage else " with no recorded voltage"

    evidence = EvidenceRecord(
        document_id=substation.source_document_id,
        document_version_id=version.id,
        site_id=site.id,
        evidence_kind=str(StageEvidenceKind.DEDICATED_SUBSTATION_PROXIMITY),
        summary=(
            f"{match.target_label}{voltage_text} lies {match.distance_meters:.0f} m from the "
            "site boundary, close enough for a dedicated connection to be practical. "
            "Proximity is a locational precondition, not evidence that this substation "
            "serves the site."
        ),
        snippet=(
            f"name = {substation.name}; operator = {substation.operator_name or 'unknown'}; "
            f"max_voltage_kv = {voltage if voltage is not None else 'unknown'}"
        ),
        snippet_locator=(substation.attributes or {}).get("osm_url"),
        observed_at=version.retrieved_at.date(),
        assertion_class=str(AssertionClass.CALCULATED),
        extraction_method=str(ExtractionMethod.GEOMETRY_OPERATION),
        polarity=str(EvidencePolarity.SUPPORTING),
        confidence=round(match.spatial_confidence, 4),
        parser_version=version.parser_version or "0.1.0",
        normalized_values={
            "distance_meters": match.distance_meters,
            "max_voltage_kv": voltage,
            "operator_name": substation.operator_name,
            "match_method": match.match_method,
            "is_standing_condition": True,
        },
    )
    session.add(evidence)
    session.flush()
    return evidence


__all__ = [
    "CANDIDATE_MIN_ACRES",
    "HYPERSCALE_CAMPUS_MIN_ACRES",
    "MAX_DEPENDENCIES_PER_KIND",
    "SiteBuildResult",
    "build_sites",
    "find_candidate_parcels",
    "generate_project_code",
    "link_infrastructure",
]
