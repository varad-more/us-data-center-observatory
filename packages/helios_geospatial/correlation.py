"""Spatial correlation between parcels, sites, and infrastructure.

Everything here runs as PostGIS queries rather than in Python. Parcel geometry
for a single county is far too large to pull into memory, and PostGIS already
has the spatial indexes and a correct geodesic distance implementation.

Distances are computed by casting to ``geography``, which measures on the
spheroid in metres. Projecting to a local UTM zone would be marginally faster but
introduces a coordinate-system assumption that silently breaks the moment Helios
covers a second region.

Every correlation records *how* it was made and how far apart the objects were,
because a 50-metre match and a 4-kilometre match are not the same claim and the
UI must be able to say so.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from helios_common.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)

ADJACENCY_TOLERANCE_METERS = 30.0
"""Parcels within this distance are treated as adjacent.

Assessor polygons are drawn to the parcel line, not the road centreline, so
genuinely abutting parcels separated by a right-of-way sit tens of metres apart.
30 m spans a typical local road reservation without bridging a section line."""

SUBSTATION_PROXIMITY_METERS = 3000.0
"""Search radius for substations that could plausibly serve a site.

Dedicated hyperscale service is normally built within a few kilometres. Beyond
this the association becomes too weak to be worth asserting even at low
confidence."""

TRANSMISSION_PROXIMITY_METERS = 2000.0


@dataclass(frozen=True, slots=True)
class SpatialMatch:
    """A spatial association with the evidence needed to judge it."""

    target_id: uuid.UUID
    target_label: str
    match_method: str
    distance_meters: float
    spatial_confidence: float
    detail: dict[str, object]


def _confidence_from_distance(distance_m: float, max_distance_m: float) -> float:
    """Convert a distance into a spatial confidence in ``[0.05, 0.95]``.

    Linear decay is used deliberately over anything more elaborate. There is no
    calibration data yet to justify a particular curve, and a simple monotonic
    function is honest about being a heuristic. Confidence is capped below 1.0
    because proximity alone never proves a relationship.

    Args:
        distance_m: Measured separation in metres.
        max_distance_m: Distance at which confidence bottoms out.

    Returns:
        A confidence value in ``[0.05, 0.95]``.
    """
    if max_distance_m <= 0:
        return 0.05
    ratio = max(0.0, min(1.0, distance_m / max_distance_m))
    return round(0.05 + (0.9 * (1.0 - ratio)), 4)


def find_adjacent_parcels(
    session: Session,
    parcel_id: uuid.UUID,
    *,
    tolerance_meters: float = ADJACENCY_TOLERANCE_METERS,
) -> list[SpatialMatch]:
    """Find parcels touching or nearly touching the given parcel.

    Adjacency is the core signal for detecting land assembly: a single 80-acre
    purchase is notable, but four abutting purchases under related entities is a
    much stronger indication of a campus being put together.

    Args:
        session: Open database session.
        parcel_id: The parcel to search around.
        tolerance_meters: Maximum gap still counted as adjacent.

    Returns:
        Adjacent parcels ordered by distance.
    """
    rows = session.execute(
        text("""
            SELECT
                other.id,
                other.apn,
                other.situs_address,
                other.owner_name_raw,
                other.lot_size_acres,
                ST_Distance(subject.geometry::geography, other.geometry::geography) AS distance_m
            FROM parcels AS subject
            JOIN parcels AS other
              ON other.id <> subject.id
             AND ST_DWithin(
                   subject.geometry::geography,
                   other.geometry::geography,
                   :tolerance
                 )
            WHERE subject.id = :parcel_id
              AND subject.geometry IS NOT NULL
              AND other.geometry IS NOT NULL
            ORDER BY distance_m
            """),
        {"parcel_id": parcel_id, "tolerance": tolerance_meters},
    ).mappings()

    return [
        SpatialMatch(
            target_id=row["id"],
            target_label=row["apn"],
            match_method="parcel_adjacency",
            distance_meters=round(float(row["distance_m"]), 2),
            spatial_confidence=_confidence_from_distance(
                float(row["distance_m"]), tolerance_meters
            ),
            detail={
                "apn": row["apn"],
                "situs_address": row["situs_address"],
                "owner_name": row["owner_name_raw"],
                "lot_size_acres": (
                    float(row["lot_size_acres"]) if row["lot_size_acres"] is not None else None
                ),
            },
        )
        for row in rows
    ]


def find_nearby_substations(
    session: Session,
    site_id: uuid.UUID,
    *,
    radius_meters: float = SUBSTATION_PROXIMITY_METERS,
    min_voltage_kv: float | None = None,
) -> list[SpatialMatch]:
    """Find substations within range of a site boundary.

    Args:
        session: Open database session.
        site_id: Site to search around.
        radius_meters: Search radius.
        min_voltage_kv: Ignore substations below this voltage.

    Returns:
        Substations ordered by distance.
    """
    rows = session.execute(
        text("""
            SELECT
                sub.id,
                sub.name,
                sub.operator_name,
                sub.max_voltage_kv,
                ST_Distance(site.boundary::geography, sub.location::geography) AS distance_m
            FROM sites AS site
            JOIN substations AS sub
              ON ST_DWithin(site.boundary::geography, sub.location::geography, :radius)
            WHERE site.id = :site_id
              AND site.boundary IS NOT NULL
              AND sub.location IS NOT NULL
              -- Explicit casts: PostgreSQL cannot infer a type for a NULL bind
              -- parameter used in an `IS NULL OR comparison` optional filter.
              AND (
                    CAST(:min_kv AS double precision) IS NULL
                 OR sub.max_voltage_kv >= CAST(:min_kv AS double precision)
              )
            ORDER BY distance_m
            """),
        {"site_id": site_id, "radius": radius_meters, "min_kv": min_voltage_kv},
    ).mappings()

    return [
        SpatialMatch(
            target_id=row["id"],
            target_label=row["name"] or "Unnamed substation",
            match_method="substation_proximity",
            distance_meters=round(float(row["distance_m"]), 2),
            spatial_confidence=_confidence_from_distance(float(row["distance_m"]), radius_meters),
            detail={
                "name": row["name"],
                "operator_name": row["operator_name"],
                "max_voltage_kv": (
                    float(row["max_voltage_kv"]) if row["max_voltage_kv"] is not None else None
                ),
            },
        )
        for row in rows
    ]


def find_nearby_transmission_lines(
    session: Session,
    site_id: uuid.UUID,
    *,
    radius_meters: float = TRANSMISSION_PROXIMITY_METERS,
) -> list[SpatialMatch]:
    """Find transmission circuits near a site.

    Note that Overpass ``out center`` gives a way's centroid rather than its
    polyline, so these distances are to the midpoint of a circuit and are
    approximate. The limitation is recorded on each match so it cannot be
    forgotten downstream.

    Args:
        session: Open database session.
        site_id: Site to search around.
        radius_meters: Search radius.

    Returns:
        Transmission lines ordered by distance.
    """
    rows = session.execute(
        text("""
            SELECT
                line.id,
                line.name,
                line.operator_name,
                line.voltage_kv,
                line.attributes,
                ST_Distance(
                    site.boundary::geography,
                    ST_SetSRID(
                        ST_MakePoint(
                            (line.attributes->>'longitude')::double precision,
                            (line.attributes->>'latitude')::double precision
                        ), 4326
                    )::geography
                ) AS distance_m
            FROM sites AS site
            JOIN transmission_lines AS line
              ON line.attributes->>'latitude' IS NOT NULL
             AND line.attributes->>'longitude' IS NOT NULL
            WHERE site.id = :site_id
              AND site.boundary IS NOT NULL
            ORDER BY distance_m
            LIMIT 50
            """),
        {"site_id": site_id},
    ).mappings()

    matches: list[SpatialMatch] = []
    for row in rows:
        distance = float(row["distance_m"])
        if distance > radius_meters:
            continue
        matches.append(
            SpatialMatch(
                target_id=row["id"],
                target_label=row["name"] or f"{row['voltage_kv']} kV circuit",
                match_method="transmission_centroid_proximity",
                distance_meters=round(distance, 2),
                # Halved because the measurement is to a way centroid, not the
                # nearest point on the circuit: the true distance is smaller and
                # unknown, so the association deserves less weight than its
                # apparent precision suggests.
                spatial_confidence=round(
                    _confidence_from_distance(distance, radius_meters) * 0.5, 4
                ),
                detail={
                    "name": row["name"],
                    "operator_name": row["operator_name"],
                    "voltage_kv": (
                        float(row["voltage_kv"]) if row["voltage_kv"] is not None else None
                    ),
                    "geometry_caveat": (
                        "Distance measured to the circuit centroid, not the nearest "
                        "point on the line; treat as an upper bound."
                    ),
                },
            )
        )
    return matches


def parcels_in_bbox(
    session: Session,
    bbox: tuple[float, float, float, float],
    *,
    land_use_filter: str | None = None,
    min_acres: float | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Query parcels intersecting a bounding box.

    Args:
        session: Open database session.
        bbox: ``(min_lon, min_lat, max_lon, max_lat)``.
        land_use_filter: Case-insensitive substring match on land-use description.
        min_acres: Minimum parcel size.
        limit: Maximum rows returned.

    Returns:
        Parcel summaries suitable for map rendering.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    rows = session.execute(
        text("""
            SELECT
                id, apn, apn_formatted, situs_address, situs_city,
                owner_name_raw, owner_is_redacted, land_use_description,
                lot_size_acres, ST_AsGeoJSON(geometry) AS geometry_json
            FROM parcels
            WHERE geometry IS NOT NULL
              AND ST_Intersects(
                    geometry,
                    ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
                  )
              AND (
                    CAST(:land_use AS text) IS NULL
                 OR land_use_description ILIKE '%%' || CAST(:land_use AS text) || '%%'
              )
              AND (
                    CAST(:min_acres AS numeric) IS NULL
                 OR lot_size_acres >= CAST(:min_acres AS numeric)
              )
            ORDER BY lot_size_acres DESC NULLS LAST
            LIMIT :limit
            """),
        {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "land_use": land_use_filter,
            "min_acres": min_acres,
            "limit": limit,
        },
    ).mappings()
    return [dict(row) for row in rows]


def compute_site_geometry(session: Session, site_id: uuid.UUID) -> dict[str, Any] | None:
    """Recompute a site's boundary, centroid, and acreage from its parcels.

    The boundary is the union of linked parcel geometries rather than a convex
    hull, so an L-shaped assembly is not misrepresented as including land the
    project does not hold.

    Args:
        session: Open database session.
        site_id: Site to recompute.

    Returns:
        The recomputed measures, or ``None`` when the site has no parcel geometry.
    """
    row = (
        session.execute(
            text("""
            WITH linked AS (
                SELECT p.geometry, p.lot_size_acres
                FROM site_parcel_links AS spl
                JOIN parcels AS p ON p.id = spl.parcel_id
                WHERE spl.site_id = :site_id
                  AND p.geometry IS NOT NULL
            )
            SELECT
                ST_AsText(ST_Multi(ST_Union(geometry))) AS boundary_wkt,
                ST_AsText(ST_Centroid(ST_Union(geometry))) AS centroid_wkt,
                SUM(lot_size_acres) AS total_acres,
                COUNT(*) AS parcel_count
            FROM linked
            """),
            {"site_id": site_id},
        )
        .mappings()
        .first()
    )

    if row is None or row["boundary_wkt"] is None:
        return None
    return {
        "boundary_wkt": row["boundary_wkt"],
        "centroid_wkt": row["centroid_wkt"],
        "total_acres": float(row["total_acres"]) if row["total_acres"] is not None else None,
        "parcel_count": int(row["parcel_count"]),
    }


__all__ = [
    "ADJACENCY_TOLERANCE_METERS",
    "SUBSTATION_PROXIMITY_METERS",
    "TRANSMISSION_PROXIMITY_METERS",
    "SpatialMatch",
    "compute_site_geometry",
    "find_adjacent_parcels",
    "find_nearby_substations",
    "find_nearby_transmission_lines",
    "parcels_in_bbox",
]
