#!/usr/bin/env python3
"""Assign every facility and event to a county, entirely offline.

This is the step that makes "how many data centres are in this area?" answerable
at any granularity without a single extra API call. Once each point carries a
county FIPS code, a county series, a state series, a metro series or any custom
grouping is a local aggregation over data already in the repository.

It also derives ``first_seen`` for each facility from its earliest creation
event. That date is **when OpenStreetMap first recorded the facility**, not when
it was built, and the column is consumed under that meaning everywhere.

Points that fall in no county are reported, never silently dropped. County
polygons are generalised, so a building within a few hundred metres of a border
can land in a sliver between two simplified outlines; those are resolved to the
nearest county within a tolerance and counted, so the fallback can never grow
unnoticed.

Run::

    python scripts/observatory/assign_regions.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from _common import (
    DATA_DIR,
    REFERENCE_DIR,
    FetchError,
    fmt_area,
    read_csv,
    write_csv,
)
from fetch_osm_history import FIELDNAMES as EVENT_FIELDNAMES
from fetch_osm_snapshot import FIELDNAMES as FACILITY_FIELDNAMES
from shapely import STRtree
from shapely.geometry import Point, shape

BOUNDARIES_PATH = REFERENCE_DIR / "counties.geojson"
FACILITIES_PATH = DATA_DIR / "facilities.csv"
EVENTS_PATH = DATA_DIR / "events.csv"
REGIONS_PATH = DATA_DIR / "regions.csv"

# ~0.02 degrees, a little over 2 km. Wide enough to absorb the generalisation
# error in the county outlines, narrow enough that a genuinely offshore or
# mis-tagged point still fails to match rather than being attached to whichever
# county happens to be closest.
NEAREST_TOLERANCE_DEGREES = 0.02

REGION_FIELDNAMES = (
    "region_id",
    "region_kind",
    "name",
    "state",
    "fips",
    "facility_count",
    "footprint_m2",
)


class CountyIndex:
    """A spatial index of county polygons supporting point lookup."""

    def __init__(self, path: Path) -> None:
        """Load boundaries from a GeoJSON file and build an STRtree.

        Args:
            path: The county boundary file written by ``fetch_county_boundaries``.

        Raises:
            FetchError: When the file is missing or carries no usable polygons.
        """
        if not path.exists():
            raise FetchError(
                f"County boundaries not found at {path}. Run "
                "`python scripts/observatory/fetch_county_boundaries.py` first."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.vintage = str(payload.get("vintage") or "unknown")
        self.geometries: list[Any] = []
        self.properties: list[dict[str, str]] = []
        for feature in payload.get("features") or []:
            try:
                geometry = shape(feature["geometry"])
            except (KeyError, ValueError, TypeError):
                continue
            if geometry.is_empty:
                continue
            self.geometries.append(geometry)
            self.properties.append(
                {
                    "fips": str(feature["properties"]["fips"]),
                    "name": str(feature["properties"]["name"]),
                    "state": str(feature["properties"]["state"]),
                }
            )
        if not self.geometries:
            raise FetchError(f"{path} contains no usable county polygons.")
        self.tree = STRtree(self.geometries)

    def lookup(self, lon: float, lat: float) -> tuple[dict[str, str] | None, bool]:
        """Find the county containing a point.

        Args:
            lon: Longitude in WGS-84 degrees.
            lat: Latitude in WGS-84 degrees.

        Returns:
            A tuple of (county properties or ``None``, whether the nearest-county
            fallback was used).
        """
        point = Point(lon, lat)
        hits = self.tree.query(point, predicate="intersects")
        if len(hits) > 0:
            return self.properties[int(hits[0])], False

        nearest = self.tree.nearest(point)
        if nearest is None:
            return None, False
        index = int(nearest)
        if self.geometries[index].distance(point) <= NEAREST_TOLERANCE_DEGREES:
            return self.properties[index], True
        return None, False


def _assign(rows: list[dict[str, str]], index: CountyIndex, label: str) -> tuple[int, int, int]:
    """Fill ``county_fips`` and ``state`` on ``rows`` in place.

    Returns:
        A tuple of (assigned, resolved by nearest-county fallback, unmatched).
    """
    assigned = fallback = unmatched = 0
    for row in rows:
        try:
            lon, lat = float(row["lon"]), float(row["lat"])
        except (KeyError, ValueError):
            unmatched += 1
            continue
        county, used_fallback = index.lookup(lon, lat)
        if county is None:
            row["county_fips"] = ""
            row["state"] = ""
            unmatched += 1
            continue
        row["county_fips"] = county["fips"]
        row["state"] = county["state"]
        assigned += 1
        fallback += int(used_fallback)
    print(
        f"  {label:<12} {assigned} assigned, {fallback} via nearest-county, {unmatched} unmatched"
    )
    return assigned, fallback, unmatched


def _first_seen(events: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    """Map each element to the date OpenStreetMap first recorded it."""
    earliest: dict[tuple[str, str], str] = {}
    for event in events:
        if event.get("event_kind") != "creation":
            continue
        key = (event["osm_type"], event["osm_id"])
        date = event["event_date"]
        if key not in earliest or date < earliest[key]:
            earliest[key] = date
    return earliest


def _build_regions(facilities: list[dict[str, str]], index: CountyIndex) -> list[dict[str, Any]]:
    """Roll facilities up into county and state region rows."""
    names = {p["fips"]: (p["name"], p["state"]) for p in index.properties}

    county_count: dict[str, int] = defaultdict(int)
    county_area: dict[str, float] = defaultdict(float)
    state_count: dict[str, int] = defaultdict(int)
    state_area: dict[str, float] = defaultdict(float)

    for facility in facilities:
        fips = facility.get("county_fips") or ""
        state = facility.get("state") or ""
        area = float(facility.get("footprint_m2") or 0.0)
        if fips:
            county_count[fips] += 1
            county_area[fips] += area
        if state:
            state_count[state] += 1
            state_area[state] += area

    rows: list[dict[str, Any]] = []
    for fips, count in county_count.items():
        name, state = names.get(fips, (fips, ""))
        rows.append(
            {
                "region_id": f"county:{fips}",
                "region_kind": "county",
                "name": name,
                "state": state,
                "fips": fips,
                "facility_count": count,
                "footprint_m2": fmt_area(county_area[fips]),
            }
        )
    for state, count in state_count.items():
        rows.append(
            {
                "region_id": f"state:{state}",
                "region_kind": "state",
                "name": state,
                "state": state,
                "fips": "",
                "facility_count": count,
                "footprint_m2": fmt_area(state_area[state]),
            }
        )

    rows.sort(key=lambda r: (str(r["region_kind"]), str(r["region_id"])))
    return rows


def main(argv: list[str] | None = None) -> int:
    """Assign regions and write the enriched files. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundaries", type=Path, default=BOUNDARIES_PATH)
    parser.add_argument("--facilities", type=Path, default=FACILITIES_PATH)
    parser.add_argument("--events", type=Path, default=EVENTS_PATH)
    parser.add_argument("--regions", type=Path, default=REGIONS_PATH)
    args = parser.parse_args(argv)

    index = CountyIndex(args.boundaries)
    print(f"Loaded {len(index.geometries)} county polygons (vintage {index.vintage})")

    facilities = read_csv(args.facilities)
    events = read_csv(args.events)
    if not facilities:
        raise FetchError(
            f"{args.facilities} is empty. Run fetch_osm_snapshot.py before assigning regions."
        )

    print("Assigning points to counties...")
    _assign(facilities, index, "facilities")
    if events:
        _assign(events, index, "events")

    # The fetch tiles are rectangles, and a rectangle covering the northern
    # United States necessarily covers southern Canada too - Toronto, Montreal
    # and Vancouver all sit inside it. Falling in a US county is the definition
    # of being in scope, so anything unmatched is dropped here rather than
    # carried as a row with no region.
    #
    # This is not cosmetic. Every foreign footprint left in the file would sit in
    # the denominator of the power allocation and shrink the share attributed to
    # each US facility.
    outside = [f for f in facilities if not f.get("county_fips")]
    if outside:
        facilities = [f for f in facilities if f.get("county_fips")]
        events = [e for e in events if e.get("county_fips")]
        sample = ", ".join(f["name"] for f in outside if f["name"])[:90]
        print(
            f"  dropped       {len(outside)} facilities in no US county "
            f"(the fetch box overlaps Canada){': ' + sample + '...' if sample else ''}"
        )

    earliest = _first_seen(events)
    dated = 0
    for facility in facilities:
        key = (facility["osm_type"], facility["osm_id"])
        if key in earliest:
            facility["first_seen"] = earliest[key]
            dated += 1
        else:
            facility["first_seen"] = ""
    print(
        f"  first_seen    {dated} of {len(facilities)} facilities dated from a creation event "
        "(mapping date, not build date)"
    )

    facilities.sort(key=lambda r: (str(r["osm_type"]), int(r["osm_id"])))
    write_csv(args.facilities, FACILITY_FIELDNAMES, facilities)
    if events:
        events.sort(
            key=lambda r: (
                str(r["event_date"]),
                str(r["osm_type"]),
                int(r["osm_id"]),
                str(r["event_kind"]),
            )
        )
        write_csv(args.events, EVENT_FIELDNAMES, events)

    regions = _build_regions(facilities, index)
    write_csv(args.regions, REGION_FIELDNAMES, regions)

    counties = [r for r in regions if r["region_kind"] == "county"]
    states = [r for r in regions if r["region_kind"] == "state"]
    print(f"\nWrote {len(regions)} regions to {args.regions}")
    print(f"  {len(counties)} counties with at least one facility, across {len(states)} states")
    top = sorted(counties, key=lambda r: int(r["facility_count"]), reverse=True)[:5]
    for row in top:
        print(f"    {row['name']}, {row['state']:<3} {row['facility_count']:>4}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nAssignment failed: {exc}", file=sys.stderr)
        sys.exit(1)
