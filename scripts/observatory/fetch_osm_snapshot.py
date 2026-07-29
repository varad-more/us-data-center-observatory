#!/usr/bin/env python3
"""Fetch the current set of US data centres from OpenStreetMap.

What this produces is a *snapshot*: every element carrying a data-centre tag at
the moment of the query, with its coordinates, its operator where a mapper
recorded one, and the area of whatever polygon was drawn. It does not say when
anything was built - OpenStreetMap does not carry that, and this script never
invents it. Dates come from :mod:`fetch_osm_history`, and they are mapping dates.

Three mechanical points decide whether this is correct:

**What the area measures.** The tags this project selects on are satisfied both
by machine halls and by the land parcels campuses sit on, and the two arrive
indistinguishable once reduced to square metres. Every row therefore carries a
``site_class`` saying which it is, so that a consumer weighting by floor area
cannot silently pick up 72 km2 of land boundary. See :func:`site_class`.

**Tiling.** A whole-country extract returns HTTP 504. Requests are therefore
tiled, and because tiles share edges, a facility can be returned by more than one
tile. Results are de-duplicated on the OSM identifier. Counting a building twice
because a grid line crossed it would inflate exactly the number this project
exists to report.

**Geodesic area.** Footprints are computed with :class:`pyproj.Geod`, which
integrates on the ellipsoid. Treating degrees as metres would overstate area at
the equator and understate it in Alaska, and footprint is the weight used to
allocate power - so an area bug would become a power bug.

Run::

    python scripts/observatory/fetch_osm_snapshot.py
    python scripts/observatory/fetch_osm_snapshot.py --tile-degrees 3 --refresh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from _common import (
    DATA_DIR,
    OSM_DATA_CENTRE_FILTERS,
    OVERPASS_MIRRORS,
    BoundingBox,
    FetchError,
    fmt_area,
    fmt_coord,
    post_form,
    read_cache,
    read_csv,
    us_tiles,
    write_cache,
    write_csv,
)
from pyproj import Geod
from shapely.geometry import Polygon

OUT_PATH = DATA_DIR / "facilities.csv"
CACHE_NAMESPACE = "osm-snapshot"

# Measured, not guessed: a 12x7-degree tile over the dense mid-Atlantic returned
# 652 elements in 11 s. Overpass cost is dominated by the index scan rather than
# by the result count, so a few large tiles beat many small ones. Lower it with
# --tile-degrees if a mirror starts timing out.
DEFAULT_TILE_DEGREES = 15.0

FIELDNAMES = (
    "osm_type",
    "osm_id",
    "name",
    "operator",
    "operator_wikidata",
    "ref",
    "lat",
    "lon",
    "footprint_m2",
    "site_class",
    "county_fips",
    "state",
    "first_seen",
)

_GEOD = Geod(ellps="WGS84")


def build_query(box: BoundingBox, timeout: int = 240) -> str:
    """Return Overpass QL selecting every data-centre element in ``box``."""
    clauses = "\n  ".join(f"{f}{box.as_overpass()};" for f in OSM_DATA_CENTRE_FILTERS)
    return f"[out:json][timeout:{timeout}];\n(\n  {clauses}\n);\nout tags geom;"


def _ring_area_m2(coords: list[tuple[float, float]]) -> float:
    """Return the geodesic area of a closed ring, in square metres."""
    if len(coords) < 4:
        return 0.0
    lons = [lon for lon, _ in coords]
    lats = [lat for _, lat in coords]
    area, _perimeter = _GEOD.polygon_area_perimeter(lons, lats)
    return abs(area)


def _coords_of(element: dict[str, Any]) -> list[tuple[float, float]]:
    """Extract a closed coordinate ring from a way element, if it has one."""
    geometry = element.get("geometry") or []
    coords = [
        (float(p["lon"]), float(p["lat"]))
        for p in geometry
        if p.get("lon") is not None and p.get("lat") is not None
    ]
    if len(coords) >= 3 and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def _outer_rings(element: dict[str, Any]) -> list[list[tuple[float, float]]]:
    """Return the outer rings of an element.

    Ways contribute their own ring. Relations contribute the rings of their
    ``outer`` members; inner members are holes and are ignored, which slightly
    overstates the footprint of a donut-shaped campus. That is a knowingly
    accepted approximation - data-centre buildings are not donuts - and it is
    recorded here rather than left for a reader to discover.
    """
    kind = element.get("type")
    if kind == "way":
        ring = _coords_of(element)
        return [ring] if len(ring) >= 4 else []
    if kind == "relation":
        rings: list[list[tuple[float, float]]] = []
        for member in element.get("members") or []:
            if member.get("role") != "outer":
                continue
            ring = _coords_of(member)
            if len(ring) >= 4:
                rings.append(ring)
        return rings
    return []


def _centroid(rings: list[list[tuple[float, float]]]) -> tuple[float, float] | None:
    """Return the area-weighted centroid of ``rings``, or ``None`` if unusable."""
    polygons = []
    for ring in rings:
        try:
            polygon = Polygon(ring)
        except (ValueError, TypeError):
            continue
        if polygon.is_valid and polygon.area > 0:
            polygons.append(polygon)
    if not polygons:
        return None
    largest = max(polygons, key=lambda p: p.area)
    point = largest.centroid
    return (float(point.x), float(point.y))


def site_class(tags: dict[str, Any], osm_type: str) -> str:
    """Classify what an element's area actually measures.

    The three tag filters this project selects on are satisfied by two entirely
    different kinds of geometry: the outline of a machine hall, and the boundary
    of the land a campus sits on. Both arrive with an area in square metres, and
    adding them together produces a number that measures nothing.

    Measured across the national snapshot, the parcels are the larger share by
    far - 174 of them cover 72 km2 against 20 km2 for 1,525 buildings - so
    treating the pooled figure as floor area does not introduce a small error,
    it inverts the result.

    Returns one of:
        ``building``      an actual structure; its area is a floor plate
        ``construction``  mapped as being built, so not yet consuming anything
        ``site``          a parcel or campus boundary; its area is land
        ``point``         a node, which carries no area at all
    """
    if tags.get("landuse") == "construction" or tags.get("building") == "construction":
        return "construction"
    if osm_type == "node":
        return "point"
    building = str(tags.get("building") or "").strip()
    # `building=no` is an explicit statement that the area is *not* a building.
    # Reading it as one put a 2 km2 land parcel into the floor-area pool and
    # sent Valencia County, New Mexico to second in the nation on six elements.
    if building and building != "no":
        return "building"
    return "site"


def normalise(element: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one Overpass element into a facility row, or ``None`` to skip."""
    tags = element.get("tags") or {}
    rings = _outer_rings(element)
    footprint = sum(_ring_area_m2(ring) for ring in rings)

    if element.get("type") == "node":
        lon, lat = element.get("lon"), element.get("lat")
        position = (float(lon), float(lat)) if lon is not None and lat is not None else None
    else:
        position = _centroid(rings)
        if position is None:
            centre = element.get("center") or {}
            if centre.get("lon") is not None:
                position = (float(centre["lon"]), float(centre["lat"]))

    if position is None:
        # No coordinate means it cannot be placed in a county or on a map. It is
        # dropped, and the count of drops is reported by the caller.
        return None

    return {
        "osm_type": str(element.get("type") or ""),
        "osm_id": str(element.get("id") or ""),
        "name": str(tags.get("name") or "").strip(),
        "operator": str(tags.get("operator") or "").strip(),
        "operator_wikidata": str(tags.get("operator:wikidata") or "").strip(),
        "ref": str(tags.get("ref") or "").strip(),
        "lat": fmt_coord(position[1]),
        "lon": fmt_coord(position[0]),
        "footprint_m2": fmt_area(footprint),
        "site_class": site_class(tags, str(element.get("type") or "")),
        # Filled in by assign_regions.py; kept in the header so the schema of the
        # file never depends on which stages have run.
        "county_fips": "",
        "state": "",
        "first_seen": "",
    }


def fetch(tile_degrees: float, *, refresh: bool) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Fetch every tile and return de-duplicated facility rows.

    Args:
        tile_degrees: Maximum tile size in degrees.
        refresh: Ignore any cached tile payloads and refetch.

    Returns:
        A tuple of (rows sorted by identifier, number of elements dropped for
        having no usable coordinate, the database timestamp each tile was served
        from).
    """
    tiles = us_tiles(tile_degrees)
    print(f"Fetching {len(tiles)} tiles at {tile_degrees} deg from Overpass...")

    by_id: dict[tuple[str, str], dict[str, Any]] = {}
    bases: list[str] = []
    dropped = 0
    for index, (label, box) in enumerate(tiles, start=1):
        cached = None if refresh else read_cache(CACHE_NAMESPACE, box.key())
        if cached is None:
            payload = post_form(
                OVERPASS_MIRRORS,
                {"data": build_query(box)},
                label=f"tile {label}",
            )
            write_cache(CACHE_NAMESPACE, box.key(), payload)
            source = "fetched"
        else:
            payload = cached
            source = "cached"

        base = str((payload.get("osm3s") or {}).get("timestamp_osm_base") or "")
        if base:
            bases.append(base)

        elements = payload.get("elements") or []
        added = 0
        for element in elements:
            row = normalise(element)
            if row is None:
                dropped += 1
                continue
            key = (row["osm_type"], row["osm_id"])
            if key not in by_id:
                by_id[key] = row
                added += 1
        print(
            f"  [{index:>3}/{len(tiles)}] {label:<16} {len(elements):>5} elements, "
            f"+{added} new ({source}, base {base[:10] or 'unknown'})"
        )

    rows = sorted(by_id.values(), key=lambda r: (str(r["osm_type"]), int(r["osm_id"])))
    return rows, dropped, bases


def main(argv: list[str] | None = None) -> int:
    """Fetch the snapshot and write ``facilities.csv``. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="Destination CSV")
    parser.add_argument(
        "--tile-degrees",
        type=float,
        default=DEFAULT_TILE_DEGREES,
        help="Maximum tile size in degrees (smaller is slower but more reliable)",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Ignore cached tiles and refetch every one"
    )
    args = parser.parse_args(argv)

    rows, dropped, bases = fetch(args.tile_degrees, refresh=args.refresh)
    if not rows:
        raise FetchError(
            "No data centres were returned by any tile. That is far more likely "
            "to be a throttled or broken query than an empty country; refusing "
            "to overwrite the dataset."
        )

    # Preserve the enrichment that assign_regions.py added on a previous run, so
    # refetching the snapshot does not silently blank the region columns.
    previous = {(r["osm_type"], r["osm_id"]): r for r in read_csv(args.out)}
    for row in rows:
        prior = previous.get((row["osm_type"], row["osm_id"]))
        if prior:
            row["county_fips"] = prior.get("county_fips", "")
            row["state"] = prior.get("state", "")
            row["first_seen"] = prior.get("first_seen", "")

    written = write_csv(args.out, FIELDNAMES, rows)
    with_footprint = sum(1 for r in rows if float(r["footprint_m2"]) > 0)
    with_operator = sum(1 for r in rows if r["operator"])
    total_area = sum(float(r["footprint_m2"]) for r in rows)

    print(f"\nWrote {written} facilities to {args.out}")
    print(f"  with footprint : {with_footprint} ({100 * with_footprint / written:.1f}%)")
    print(f"  with operator  : {with_operator} ({100 * with_operator / written:.1f}%)")
    print(f"  total footprint: {total_area / 1_000_000:.2f} km2")
    if dropped:
        print(f"  dropped (no coordinate): {dropped}")

    # Mirrors do not all replicate at the same rate - one observed instance was
    # two months behind another. Tiles served from different vintages would make
    # the snapshot internally inconsistent, so the spread is always reported and
    # a wide one is called out rather than left to be discovered later.
    if bases:
        oldest, newest = min(bases), max(bases)
        print(f"  osm database   : {oldest[:10]} to {newest[:10]}")
        if oldest[:10] != newest[:10]:
            print(
                "  WARNING: tiles were served from databases of different dates. "
                "Re-run with --refresh once mirrors agree if this spread is large."
            )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nFetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
