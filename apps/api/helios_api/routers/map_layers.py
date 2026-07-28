"""GeoJSON layers for the interactive map."""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from helios_api.deps import BoundingBox, DbSession
from helios_api.schemas import MapFeatureCollection
from helios_domain.ontology import DevelopmentStage

router = APIRouter(prefix="/map", tags=["map"])

DEFAULT_BBOX = (-111.98, 33.16, -111.35, 33.52)
"""East Valley study area, used when the client does not supply a viewport."""

CONTINENTAL_US_BBOX = (-125.0, 24.0, -66.5, 49.5)
"""Default viewport for the one layer that is national rather than regional.

Deliberately excludes Alaska and Hawaii: neither appears in the hosting-NAICS
sweep, and stretching the box to hold them would shrink everything else."""


def _feature(geometry_json: str | None, properties: dict[str, Any]) -> dict[str, Any] | None:
    """Build a GeoJSON feature, skipping rows without geometry."""
    if not geometry_json:
        return None
    return {
        "type": "Feature",
        "geometry": json.loads(geometry_json),
        "properties": properties,
    }


@router.get("/sites", response_model=MapFeatureCollection, summary="Site boundaries as GeoJSON")
def map_sites(
    session: DbSession,
    bbox: BoundingBox = None,
    min_confidence: Annotated[float, Query(ge=0, le=100)] = 0.0,
) -> MapFeatureCollection:
    """Return site boundaries with the properties the map needs to style them."""
    min_lon, min_lat, max_lon, max_lat = bbox or DEFAULT_BBOX
    rows = session.execute(
        text("""
            SELECT
                s.id, s.project_code, s.site_kind, s.site_kind_assertion,
                s.current_stage, s.current_confidence, s.jurisdiction,
                s.total_acres, s.first_signal_date, s.latest_signal_date,
                s.evidence_count,
                ST_AsGeoJSON(s.boundary) AS geometry_json
            FROM sites AS s
            WHERE s.boundary IS NOT NULL
              AND s.current_confidence >= :min_confidence
              AND ST_Intersects(
                    s.boundary,
                    ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
                  )
            ORDER BY s.current_confidence DESC
            LIMIT 1000
            """),
        {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "min_confidence": min_confidence,
        },
    ).mappings()

    features = []
    for row in rows:
        stage = DevelopmentStage(row["current_stage"])
        feature = _feature(
            row["geometry_json"],
            {
                "id": str(row["id"]),
                "project_code": row["project_code"],
                "site_kind": row["site_kind"],
                "site_kind_assertion": row["site_kind_assertion"],
                "stage": row["current_stage"],
                "stage_label": stage.label,
                "confidence": round(float(row["current_confidence"]), 1),
                "jurisdiction": row["jurisdiction"],
                "total_acres": (
                    float(row["total_acres"]) if row["total_acres"] is not None else None
                ),
                "evidence_count": row["evidence_count"],
                "first_signal_date": (
                    row["first_signal_date"].isoformat() if row["first_signal_date"] else None
                ),
                "latest_signal_date": (
                    row["latest_signal_date"].isoformat() if row["latest_signal_date"] else None
                ),
            },
        )
        if feature:
            features.append(feature)

    return MapFeatureCollection(
        features=features,
        attributions=["Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS."],
    )


@router.get("/parcels", response_model=MapFeatureCollection, summary="Parcels as GeoJSON")
def map_parcels(
    session: DbSession,
    bbox: BoundingBox = None,
    land_use: Annotated[str | None, Query(description="Land-use substring filter")] = None,
    min_acres: Annotated[float | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> MapFeatureCollection:
    """Return parcel polygons, honouring owner redaction."""
    from helios_geospatial.correlation import parcels_in_bbox

    box = bbox or DEFAULT_BBOX
    rows = parcels_in_bbox(session, box, land_use_filter=land_use, min_acres=min_acres, limit=limit)

    features = []
    for row in rows:
        feature = _feature(
            row["geometry_json"],
            {
                "id": str(row["id"]),
                "apn": row["apn"],
                "apn_formatted": row["apn_formatted"],
                "situs_address": row["situs_address"],
                "situs_city": row["situs_city"],
                "owner_name": None if row["owner_is_redacted"] else row["owner_name_raw"],
                "owner_is_redacted": row["owner_is_redacted"],
                "land_use_description": row["land_use_description"],
                "lot_size_acres": (
                    float(row["lot_size_acres"]) if row["lot_size_acres"] is not None else None
                ),
            },
        )
        if feature:
            features.append(feature)

    return MapFeatureCollection(
        features=features,
        attributions=["Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS."],
    )


@router.get(
    "/infrastructure",
    response_model=MapFeatureCollection,
    summary="Power infrastructure as GeoJSON",
)
def map_infrastructure(
    session: DbSession,
    bbox: BoundingBox = None,
    min_voltage_kv: Annotated[float | None, Query(ge=0)] = None,
) -> MapFeatureCollection:
    """Return substations within the viewport."""
    min_lon, min_lat, max_lon, max_lat = bbox or DEFAULT_BBOX
    rows = session.execute(
        text("""
            SELECT
                id, name, operator_name, max_voltage_kv, status, attributes,
                ST_AsGeoJSON(location) AS geometry_json
            FROM substations
            WHERE location IS NOT NULL
              AND ST_Intersects(
                    location,
                    ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
                  )
              AND (
                    CAST(:min_kv AS double precision) IS NULL
                 OR max_voltage_kv >= CAST(:min_kv AS double precision)
              )
            ORDER BY max_voltage_kv DESC NULLS LAST
            LIMIT 1000
            """),
        {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "min_kv": min_voltage_kv,
        },
    ).mappings()

    features = []
    for row in rows:
        feature = _feature(
            row["geometry_json"],
            {
                "id": str(row["id"]),
                "kind": "substation",
                "name": row["name"],
                "operator_name": row["operator_name"],
                "max_voltage_kv": (
                    float(row["max_voltage_kv"]) if row["max_voltage_kv"] is not None else None
                ),
                "status": row["status"],
                "osm_url": (row["attributes"] or {}).get("osm_url"),
            },
        )
        if feature:
            features.append(feature)

    return MapFeatureCollection(
        features=features,
        attributions=["Power infrastructure data (c) OpenStreetMap contributors, ODbL."],
    )


@router.get(
    "/facilities",
    response_model=MapFeatureCollection,
    summary="Reported hosting facilities as GeoJSON",
)
def map_facilities(
    session: DbSession,
    bbox: BoundingBox = None,
    state: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> MapFeatureCollection:
    """Return EPA-reported hosting facilities, nationwide by default.

    These are not sites. A facility here is one federal record saying a permitted
    Clean Air Act facility carries a hosting NAICS code; a Helios site is a
    hypothesis assembled from county parcels and defensible line by line. The
    viewport defaults to the continental United States rather than the study
    area, because unlike every other layer this one is not regional.
    """
    min_lon, min_lat, max_lon, max_lat = bbox or CONTINENTAL_US_BBOX
    rows = session.execute(
        text("""
            SELECT
                p.id, p.description, p.jurisdiction, p.status, p.attributes,
                p.site_id,
                ST_AsGeoJSON(p.location) AS geometry_json
            FROM permits AS p
            JOIN sources AS src ON src.id = p.source_id
            WHERE p.location IS NOT NULL
              AND src.slug = 'epa-echo-air-facilities'
              AND (CAST(:state AS text) IS NULL OR p.attributes->>'state' = CAST(:state AS text))
              AND ST_Intersects(
                    p.location,
                    ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
                  )
            ORDER BY p.description
            LIMIT 2000
            """),
        {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
            "state": state.upper() if state else None,
        },
    ).mappings()

    features = []
    for row in rows:
        attributes = row["attributes"] or {}
        feature = _feature(
            row["geometry_json"],
            {
                "id": str(row["id"]),
                "kind": "reported_facility",
                "name": row["description"],
                "jurisdiction": row["jurisdiction"],
                "state": attributes.get("state"),
                "county_fips": attributes.get("county_fips"),
                "naics": attributes.get("naics"),
                "status": row["status"],
                # Whether this record was matched to a Helios site. Nearly always
                # false, and visibly so: matching needs parcels.
                "linked_to_site": row["site_id"] is not None,
            },
        )
        if feature:
            features.append(feature)

    return MapFeatureCollection(
        features=features,
        attributions=[
            "Facility records from US EPA ECHO (ICIS-Air), public domain. "
            "Coordinates are sometimes geocoded rather than surveyed."
        ],
    )


__all__ = ["router"]
