#!/usr/bin/env python3
"""Fetch US county boundaries from the Census Bureau, once.

County polygons are what let every other stage aggregate offline. With them in
the repository, the growth curve for any county, state or custom area is a
point-in-polygon test over data already on disk - no per-region API call, which
is what makes county-level granularity affordable at all.

Source is the Census TIGERweb ArcGIS REST service, the authoritative publisher.
Helios already speaks this API for the Maricopa assessor layer, so no new access
method is introduced. Geometry is generalised server-side via
``maxAllowableOffset``: county borders are needed to place buildings, not to
settle boundary disputes, and the full-resolution file is an order of magnitude
larger for no gain here.

The vintage is recorded in the output. County FIPS codes are not eternal -
Connecticut replaced its eight counties with nine planning regions in 2022 - so
a dataset keyed by FIPS has to say which year's map it used.

Run::

    python scripts/observatory/fetch_county_boundaries.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from _common import REFERENCE_DIR, FetchError, get_json

TIGERWEB_COUNTIES = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services"
    "/TIGERweb/State_County/MapServer/1/query"
)

# ~220 m at the equator. Comfortably finer than the placement error that matters
# when assigning a building to a county, and it keeps the file committable.
SIMPLIFY_DEGREES = 0.002

# 5 decimal places is ~1.1 m. Storing more would inflate the file with digits
# that the simplification above has already made meaningless.
COORD_DECIMALS = 5

OUT_PATH = REFERENCE_DIR / "counties.geojson"

# Every state, DC and the inhabited territories. Keyed by the two-digit state
# FIPS the Census assigns, because the county layer carries that code and not a
# postal abbreviation.
STATE_FIPS_TO_CODE: dict[str, str] = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
    "60": "AS",
    "66": "GU",
    "69": "MP",
    "72": "PR",
    "78": "VI",
}


def _round_coords(geometry: Any) -> Any:
    """Recursively round coordinate values to :data:`COORD_DECIMALS`."""
    if isinstance(geometry, list):
        return [_round_coords(item) for item in geometry]
    if isinstance(geometry, float):
        return round(geometry, COORD_DECIMALS)
    return geometry


def fetch_counties() -> dict[str, Any]:
    """Fetch every county polygon as GeoJSON.

    Returns:
        A GeoJSON FeatureCollection with generalised geometry and a trimmed
        property set.

    Raises:
        FetchError: When the service answers with no features, which would
            otherwise silently produce a boundary file that matches nothing.
    """
    print(f"Fetching county boundaries from TIGERweb (simplify={SIMPLIFY_DEGREES} deg)...")
    payload = get_json(
        TIGERWEB_COUNTIES,
        {
            "where": "1=1",
            "outFields": "GEOID,STATE,COUNTY,NAME,BASENAME",
            "returnGeometry": "true",
            "outSR": "4326",
            "maxAllowableOffset": str(SIMPLIFY_DEGREES),
            "f": "geojson",
        },
    )
    features = payload.get("features") or []
    if not features:
        raise FetchError(
            "TIGERweb returned no county features. Refusing to write an empty "
            "boundary file: every later stage would report zero coverage."
        )

    cleaned: list[dict[str, Any]] = []
    unknown_states: set[str] = set()
    for feature in features:
        props = feature.get("properties") or {}
        geoid = str(props.get("GEOID") or "").strip()
        state_fips = str(props.get("STATE") or "").strip()
        if not geoid or not feature.get("geometry"):
            continue
        state_code = STATE_FIPS_TO_CODE.get(state_fips)
        if state_code is None:
            unknown_states.add(state_fips)
            continue
        cleaned.append(
            {
                "type": "Feature",
                "properties": {
                    "fips": geoid,
                    "name": str(props.get("NAME") or "").strip(),
                    "state": state_code,
                },
                "geometry": _round_coords(feature["geometry"]),
            }
        )

    if unknown_states:
        print(f"  skipped {len(unknown_states)} unrecognised state FIPS: {sorted(unknown_states)}")

    cleaned.sort(key=lambda f: str(f["properties"]["fips"]))
    return {
        "type": "FeatureCollection",
        "vintage": datetime.now(tz=UTC).strftime("%Y"),
        "retrieved_at": datetime.now(tz=UTC).date().isoformat(),
        "source": "US Census Bureau TIGERweb, State_County/MapServer layer 1",
        "note": (
            "Geometry generalised server-side for point-in-county assignment. "
            "Not suitable for boundary-accurate work. County FIPS codes change "
            "over time; this file records the vintage it was drawn from."
        ),
        "features": cleaned,
    }


def main(argv: list[str] | None = None) -> int:
    """Fetch and write the boundary file. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="Destination GeoJSON path")
    args = parser.parse_args(argv)

    collection = fetch_counties()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(collection, separators=(",", ":")) + "\n", encoding="utf-8")

    states = {str(f["properties"]["state"]) for f in collection["features"]}
    size_mb = args.out.stat().st_size / 1_000_000
    print(
        f"Wrote {len(collection['features'])} counties across {len(states)} states "
        f"to {args.out.relative_to(Path.cwd()) if args.out.is_absolute() else args.out} "
        f"({size_mb:.1f} MB)"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nFetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
