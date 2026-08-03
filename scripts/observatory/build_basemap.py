#!/usr/bin/env python3
"""Dissolve the county boundaries into one coastline for the plot sheet.

The front page draws every mapped facility over the 61,983 substations and power
plants on the sheet. That density field is real evidence and it does trace the
populated parts of the country - but a reader cannot find Nevada in a stipple,
because nothing is there to stipple. Two rounds of tuning the marks did not fix
that, and no amount of tuning could: a density field is a measurement, not a
map, and the shape of a country is the one thing it cannot be asked to carry.

So this writes the outline separately. It is reference geography, not an
observation, and the sheet draws it in the paper's own hairline rather than in
any of the pens - the same distinction the rest of the site holds between the
printed grid on a chart recorder's paper and the ink the instrument lays on it.

The source is the county file already committed for point-in-polygon work.
Dissolving it rather than fetching a second boundary file means the coastline on
the sheet is the same coastline that decided which county every facility is in;
one file cannot drift from the other because there is only one file.

That file was generalised server-side per feature, so adjacent counties do not
share vertices and their borders cross and re-cross by a few metres. Edge
de-duplication - the obvious way to dissolve a clean topology - therefore leaves
78,016 interior segments looking like coastline. ``unary_union`` heals that; the
``buffer(0)`` on each polygon first is what makes it survive the self-touching
rings the generalisation also produced.

Alaska, Hawaii and the territories are excluded because the sheet is fitted to
the contiguous states: an extent stretched to the Aleutians shrinks the lower 48
to a third of the paper. No mapped facility is in Alaska or Hawaii; the two in
Puerto Rico get their own inset, projected at true relative area.

Output is lon/lat, not projected. The projection belongs to whatever draws it,
and the sheet already owns an Albers.

Run::

    python scripts/observatory/build_basemap.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _common import REFERENCE_DIR, REPO_ROOT, FetchError
from shapely.geometry import shape
from shapely.ops import unary_union

IN_PATH = REFERENCE_DIR / "counties.geojson"
OUT_PATH = REPO_ROOT / "apps" / "web" / "public" / "data" / "basemap.json"

# Everything outside the contiguous states. DC is a state code here and stays.
NON_CONUS = frozenset({"AK", "HI", "PR", "VI", "GU", "AS", "MP"})

# 0.02 degrees is about 2 km, which is 0.4 px on the 1000-px-wide sheet. Fine
# enough that Chesapeake Bay, Puget Sound, Cape Cod and the Florida Keys all
# survive; coarse enough that the whole coastline is 15 kB of path data instead
# of 200 kB, and this markup is emitted twice - once as HTML and once into the
# payload that hydrates the page.
SIMPLIFY_DEGREES = 0.02

# About 90 km2 at these latitudes: an island smaller than this is under two pixels
# on the sheet and reads as dirt on the paper. Long Island, Martha's Vineyard,
# the Channel Islands and the Outer Banks are all comfortably above it.
MIN_FEATURE_DEG2 = 0.008

# 0.001 degrees is about 110 m, or 0.02 px once drawn. More digits than that
# would be storing the simplifier's rounding error.
COORD_DECIMALS = 3


def dissolve(features: list[dict[str, Any]]) -> Any:
    """Union every contiguous-state county into one land geometry."""
    polygons = [
        # buffer(0) repairs the self-intersections that server-side
        # generalisation leaves behind. Without it the union raises on the first
        # bow-tie ring and takes the whole coastline with it.
        shape(f["geometry"]).buffer(0)
        for f in features
        if f.get("properties", {}).get("state") not in NON_CONUS
    ]
    if not polygons:
        raise FetchError(
            f"{IN_PATH} holds no contiguous-state counties. Run "
            "fetch_county_boundaries.py before this stage."
        )
    return unary_union(polygons)


def rings(geometry: Any) -> list[list[list[float]]]:
    """The simplified outline as closed exterior rings of lon/lat, largest first.

    Interiors are discarded outright, and that is a statement about the source
    rather than a shortcut. Counties tile their states completely, water
    included, so a hole inside the union cannot be a lake or a bay - it can only
    be two counties disagreeing about where their shared border runs. There are
    17,500 of them, every one a sliver: the largest traces 110 km of the
    Kansas-Nebraska line at 2 km wide, which is far too big for any area
    threshold to catch and drew as a stray dash across Kansas.
    """
    simplified = geometry.simplify(SIMPLIFY_DEGREES, preserve_topology=True)
    parts = list(simplified.geoms) if simplified.geom_type == "MultiPolygon" else [simplified]
    return [
        [
            [round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS)]
            for lon, lat in polygon.exterior.coords
        ]
        for polygon in sorted(parts, key=lambda p: p.area, reverse=True)
        if polygon.area >= MIN_FEATURE_DEG2
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    if not IN_PATH.exists():
        raise FetchError(f"{IN_PATH} is missing. Run fetch_county_boundaries.py first.")
    source = json.loads(IN_PATH.read_text(encoding="utf-8"))

    land = rings(dissolve(source["features"]))
    if len(land) < 1 or len(land[0]) < 500:
        # The mainland ring is ~1,200 points. Anything close to empty means the
        # union collapsed, and writing it would replace a working coastline with
        # a shape that is silently not a country.
        raise FetchError(
            f"dissolved outline looks wrong: {len(land)} rings, "
            f"largest {len(land[0]) if land else 0} points."
        )

    payload = {
        "source": source.get("source", ""),
        "vintage": source.get("vintage", ""),
        "note": (
            "Contiguous-state land outline, dissolved from the committed county "
            "boundaries. Generalised for drawing at page scale, not for "
            "boundary-accurate work. Reference geography, not an observation."
        ),
        "simplify_degrees": SIMPLIFY_DEGREES,
        "min_feature_deg2": MIN_FEATURE_DEG2,
        "rings": land,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":")) + "\n"
    args.out.write_text(text, encoding="utf-8")

    points = sum(len(r) for r in land)
    print(f"basemap.json  {len(land)} rings, {points} points, {len(text) // 1024} kB")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
