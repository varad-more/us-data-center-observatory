#!/usr/bin/env python3
"""Turn the observatory CSVs into the static JSON the published site reads.

GitHub Pages serves files, not queries, so every view the site offers has to
exist as a file before deployment. This script writes them. It needs no
database, no API and no network - the CSVs in ``data/observatory`` are the whole
input, which is what lets a contributor rebuild the site from a clean checkout.

Series are written one file per region rather than as a single bundle. A visitor
looking at Loudoun County should not download Alameda County's history to see
it, and a per-region file is the simplest thing that has that property.

Run::

    python scripts/observatory/build_site_data.py
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from _common import DATA_DIR, REPO_ROOT, FetchError, read_csv

OUT_DIR = REPO_ROOT / "apps" / "web" / "public" / "data"

FACILITIES_PATH = DATA_DIR / "facilities.csv"
GRID_PATH = DATA_DIR / "grid.csv"
GRID_REGIONS_PATH = DATA_DIR / "grid_regions.csv"
REGIONS_PATH = DATA_DIR / "regions.csv"
SERIES_PATH = DATA_DIR / "region_series.csv"
EVENTS_PATH = DATA_DIR / "events.csv"
NATIONAL_PATH = DATA_DIR / "national_energy.csv"
POLL_LOG_PATH = DATA_DIR / "poll_log.csv"

# How many of the most recent months of change the front page summarises.
RECENT_MONTHS = 24

# Facilities are emitted as GeoJSON for the map. Tags a mapper did not fill in
# are omitted rather than sent as empty strings, which keeps the file smaller and
# stops the UI from rendering a blank where it should render nothing.
FACILITY_KEYS = ("name", "operator", "ref", "county_fips", "state", "first_seen")


def _last_polled() -> str:
    """The date the public sources were last actually contacted.

    A wall-clock timestamp here would be the one field in the whole payload that
    changes on a run that changed nothing, and it broke the property the rest of
    the pipeline is built to have: identical inputs produce identical bytes, so a
    diff always means real movement. It was also the less useful of the two
    dates. A reader wants to know how current the data is, not when a script last
    ran over it.

    ``poll_log.csv`` gains a row only when a fetch really happened, so its last
    entry answers that and is stable across rebuilds. An empty log means the
    dataset has never been polled, which is reported as unknown rather than as
    today.
    """
    log = read_csv(POLL_LOG_PATH)
    return str(log[-1].get("polled_at", "")) if log else ""


def _write(path: Path, payload: Any) -> int:
    """Write ``payload`` as compact JSON and return the byte count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"), sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return len(text)


def build_facilities(
    facilities: list[dict[str, str]], national_mw: float, total_area: float
) -> Any:
    """Build the GeoJSON point layer for the map."""
    features = []
    for row in facilities:
        try:
            lon, lat = float(row["lon"]), float(row["lat"])
        except (KeyError, ValueError):
            continue
        area = float(row.get("footprint_m2") or 0.0)
        kind = row.get("site_class") or ""
        properties: dict[str, Any] = {
            "id": f"{row['osm_type']}/{row['osm_id']}",
            "footprint_m2": round(area),
        }
        if kind:
            properties["site_class"] = kind
        for key in FACILITY_KEYS:
            value = row.get(key)
            if value:
                properties[key] = value
        # Only a building carries a power figure. A land parcel's area is not a
        # floor plate and a construction site is not consuming anything yet, so
        # both are left without the key entirely - absent reads as unknown,
        # where a zero would read as a measured nothing.
        if kind == "building" and total_area > 0:
            properties["est_mw"] = round(area / total_area * national_mw, 2)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def build_grid(rows: list[dict[str, str]]) -> Any:
    """Build the GeoJSON point layer for substations and generating plants.

    Only assets inside a US county are published. The Overpass boxes this was
    fetched with reach into Sonora, Chihuahua, Ontario and the Gulf, and 2,898
    of the 65,325 rows are outside every county in the file - so an unfiltered
    layer draws Mexican and Canadian substations on a map captioned "the
    contiguous states", and counts them in a national total. The county totals
    were always right, because they are keyed on the assignment; the map and the
    headline figure were the two surfaces that read the raw rows.

    Coordinates are cut to five decimals - about a metre - because this layer is
    read at national zoom and the sixth decimal would add roughly 40 KB across
    42,000 points to place a substation no more accurately than its own fence.

    Empty tags are omitted rather than sent as blanks. At this row count that is
    the difference between a file the map can fetch on demand and one it cannot.
    """
    features = []
    for row in rows:
        if not row.get("county_fips"):
            continue
        try:
            lon, lat = round(float(row["lon"]), 5), round(float(row["lat"]), 5)
        except (KeyError, ValueError):
            continue
        properties: dict[str, Any] = {"kind": row["kind"]}
        for key in ("name", "operator", "source"):
            if row.get(key):
                properties[key] = row[key]
        for key in ("voltage_kv", "capacity_mw"):
            if row.get(key):
                with contextlib.suppress(ValueError):
                    properties[key] = float(row[key])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _grid_fields(row: dict[str, str] | None) -> dict[str, Any]:
    """Return a region's grid summary, or nothing at all when it has none."""
    if not row:
        return {}
    return {
        "substation_count": int(row["substation_count"]),
        "bulk_substation_count": int(row["bulk_substation_count"]),
        "max_voltage_kv": float(row["max_voltage_kv"]),
        "plant_count": int(row["plant_count"]),
        "plant_capacity_mw": float(row["plant_capacity_mw"]),
        "plants_without_capacity": int(row["plants_without_capacity"]),
    }


def build_series_files(series: list[dict[str, str]], out_dir: Path) -> int:
    """Write one JSON file per region series. Returns the number written."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in series:
        grouped[row["region_id"]].append(
            {
                "period": row["period"],
                "count": int(row["cumulative_count"]),
                "change": int(row["net_change"]),
                "footprint_m2": round(float(row["cumulative_footprint_m2"])),
            }
        )
    for region_id, points in grouped.items():
        _write(
            out_dir / f"{region_id.replace(':', '-')}.json",
            {"region_id": region_id, "points": points},
        )
    return len(grouped)


def main(argv: list[str] | None = None) -> int:
    """Build every static payload. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)

    facilities = read_csv(FACILITIES_PATH)
    grid = read_csv(GRID_PATH)
    grid_regions = read_csv(GRID_REGIONS_PATH)
    regions = read_csv(REGIONS_PATH)
    series = read_csv(SERIES_PATH)
    events = read_csv(EVENTS_PATH)
    national = read_csv(NATIONAL_PATH)

    if not facilities or not regions:
        raise FetchError(
            "facilities.csv and regions.csv must exist. Run the fetch and assign "
            "stages before building site data."
        )

    historical = [r for r in national if r.get("series_kind") == "historical"]
    electricity = [r for r in historical if r.get("electricity_twh")]
    if not electricity:
        raise FetchError("national_energy.csv carries no historical electricity figure.")
    latest = max(electricity, key=lambda r: int(r["year"]))
    national_mw = float(latest["electricity_twh"]) * 1e12 / 8760 / 1e6
    # Building floor area only, matching allocate_power.py's denominator. Pooling
    # in land parcels here would put a different national total behind the map
    # than the one behind the region pages.
    total_area = sum(
        float(f.get("footprint_m2") or 0.0) for f in facilities if f.get("site_class") == "building"
    )

    written: dict[str, int] = {}
    written["facilities.geojson"] = _write(
        args.out / "facilities.geojson",
        build_facilities(facilities, national_mw, total_area),
    )

    # Written even when empty so the map's fetch gets a valid, obviously empty
    # layer rather than a 404 it would have to interpret.
    written["grid.geojson"] = _write(args.out / "grid.geojson", build_grid(grid))

    # Grid totals are merged in by region_id rather than joined in the browser.
    # They are optional: a region with no grid row carries no grid keys at all,
    # so the UI can distinguish "no substations mapped here" from "this dataset
    # has not been built yet" instead of rendering both as zero.
    grid_by_region = {r["region_id"]: r for r in grid_regions}

    written["regions.json"] = _write(
        args.out / "regions.json",
        {
            "items": [
                {
                    **_grid_fields(grid_by_region.get(r["region_id"])),
                    "region_id": r["region_id"],
                    "kind": r["region_kind"],
                    "name": r["name"],
                    "state": r["state"],
                    "fips": r["fips"],
                    "facility_count": int(r["facility_count"]),
                    "building_count": int(r.get("building_count") or 0),
                    "site_count": int(r.get("site_count") or 0),
                    "construction_count": int(r.get("construction_count") or 0),
                    "footprint_m2": round(float(r["footprint_m2"])),
                    "site_area_m2": round(float(r.get("site_area_m2") or 0.0)),
                    "construction_area_m2": round(float(r.get("construction_area_m2") or 0.0)),
                    "est_mw": float(r.get("est_mw") or 0.0),
                    "est_gal_per_day": float(r.get("est_gal_per_day") or 0.0),
                }
                for r in regions
            ]
        },
    )

    written["national_energy.json"] = _write(
        args.out / "national_energy.json",
        {
            "items": [
                {
                    "year": int(r["year"]),
                    "electricity_twh": (
                        float(r["electricity_twh"]) if r["electricity_twh"] else None
                    ),
                    "water_bgal": float(r["water_bgal"]) if r["water_bgal"] else None,
                    "series_kind": r["series_kind"],
                    "scenario": r["scenario"],
                    "assertion_class": r["assertion_class"],
                    "source": r["source"],
                }
                for r in national
            ]
        },
    )

    series_count = 0
    if series:
        series_count = build_series_files(series, args.out / "series")

    # Names come from the current snapshot, so an appearance is usually named and
    # a removal usually is not - the facility is gone from the map by the time
    # anyone reads this. That asymmetry is honest and is left visible.
    names = {(f["osm_type"], f["osm_id"]): f.get("name", "") for f in facilities}
    county_names = {
        r["fips"]: f"{r['name']}, {r['state']}"
        for r in regions
        if r.get("region_kind") == "county" and r.get("fips")
    }

    recent = sorted(
        (e for e in events if e.get("event_kind") in {"creation", "deletion"}),
        key=lambda e: str(e["event_date"]),
        reverse=True,
    )[:500]
    written["changes.json"] = _write(
        args.out / "changes.json",
        {
            "items": [
                {
                    "id": f"{e['osm_type']}/{e['osm_id']}",
                    "date": e["event_date"],
                    "kind": e["event_kind"],
                    "state": e.get("state", ""),
                    "county_fips": e.get("county_fips", ""),
                    "name": names.get((e["osm_type"], e["osm_id"]), ""),
                    "county_name": county_names.get(e.get("county_fips", ""), ""),
                }
                for e in recent
            ]
        },
    )

    written["meta.json"] = _write(
        args.out / "meta.json",
        {
            "last_polled": _last_polled(),
            "facility_count": len(facilities),
            "building_count": sum(1 for f in facilities if f.get("site_class") == "building"),
            "construction_count": sum(
                1 for f in facilities if f.get("site_class") == "construction"
            ),
            "region_count": len(regions),
            "series_count": series_count,
            # US only, on the same test the published layer uses. Every page
            # that prints these calls them the grid the American facilities
            # connect to, and 2,898 of the raw rows are in Mexico, Canada or
            # offshore.
            "substation_count": sum(
                1 for r in grid if r.get("kind") == "substation" and r.get("county_fips")
            ),
            "plant_count": sum(
                1 for r in grid if r.get("kind") == "plant" and r.get("county_fips")
            ),
            "national_mw": round(national_mw),
            "national_reference_year": int(latest["year"]),
            "total_footprint_m2": round(total_area),
            "note": (
                "Facility locations and footprints are reported by OpenStreetMap "
                "contributors. Dates are when OpenStreetMap first recorded a "
                "facility, not when it was built - OpenStreetMap carries no build "
                "dates. Power and water are a facility's share of a reported "
                "national total, allocated by building floor area, and are upper "
                "bounds. Only buildings carry that share: a campus mapped as a land "
                "parcel and a site mapped as under construction are counted and "
                "measured, but are given no power or water figure at all."
            ),
        },
    )

    print(f"Wrote site data to {args.out}")
    for name, size in written.items():
        print(f"  {name:<24} {size / 1024:>8.1f} KB")
    if series_count:
        print(f"  series/{'':<17} {series_count} region files")
    else:
        print("  series/                  none - run fetch_osm_history.py and build_series.py")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nBuild failed: {exc}", file=sys.stderr)
        sys.exit(1)
