#!/usr/bin/env python3
"""Fetch US electricity grid infrastructure from OpenStreetMap.

Data centres are sited where the grid can carry them, so the map is far more
informative with the grid drawn under it. This script collects the two asset
classes that decide that: **substations** at transmission voltage, and
**generating plants**.

Four decisions shape what comes back, and each of them is a correctness matter
rather than a preference:

**The voltage filter has to survive lists.** OpenStreetMap records ``voltage``
as a semicolon-separated list wherever a substation transforms between levels -
``115000;230000`` and ``69000;138000;345000`` are ordinary values. An anchored
regex over the whole tag would match none of them, and the substations it
dropped would be precisely the large multi-voltage ones this layer exists to
show. The filter therefore matches any member of the list, and the kilovolt
figure written out is the maximum of them.

**Points, not outlines.** A substation is requested with ``out tags center``.
The yard outline is not what the map needs at national zoom, and asking for full
geometry would multiply the payload for detail no reader would ever see.

**Generators are not plants.** ``power=generator`` is a single unit - one wind
turbine, one roof of solar panels - and there are 22,854 of them in Virginia
alone. ``power=plant`` is the facility. Only the latter is collected.

**69 kV is the floor**, matching the threshold the Arizona site map already
uses, so the two views of the grid agree about what counts as transmission.

Run::

    python scripts/observatory/fetch_grid.py
    python scripts/observatory/fetch_grid.py --tile-degrees 8 --refresh
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from _common import (
    DATA_DIR,
    OVERPASS_MIRRORS,
    BoundingBox,
    FetchError,
    fmt_coord,
    iter_progress,
    post_form,
    read_cache,
    us_tiles,
    write_cache,
    write_csv,
)

OUT_PATH = DATA_DIR / "grid.csv"
CACHE_NAMESPACE = "osm-grid"

# Substations below this are distribution, not transmission. A data centre's
# constraint is the transmission connection, and including every pole-mounted
# 12 kV yard would bury the signal under two orders of magnitude of noise.
MIN_VOLTAGE_V = 69_000

# Matches a transmission voltage anywhere in a semicolon-separated list: 69000
# to 69999, five digits starting 7-9 (70-99 kV), or any number of six digits or
# more (100 kV+). Overpass evaluates this server-side purely to keep the
# transfer small; the authoritative filter is `max_voltage_v` below, which
# parses every value.
#
# The `69[0-9]{3}` branch is not redundant. Without it the pattern begins at
# 70 kV and silently drops every substation tagged exactly 69000 - which is both
# the threshold itself and one of the most widely used sub-transmission voltages
# in the United States. A unit test holds this, because the failure mode is a
# quieter map rather than an error.
VOLTAGE_PATTERN = r"(^|;)(69[0-9]{3}|[7-9][0-9]{4}|[1-9][0-9]{5,})(;|$)"

# Measured: a whole-CONUS count of these two filters answered in 49 s and 36 s,
# so the index scan - not the result count - is the cost. Around 42,000 elements
# nationally is a trivial transfer spread over a handful of tiles, and fewer
# tiles means fewer scans. Small enough to resume from, large enough not to pay
# the scan sixty times.
DEFAULT_TILE_DEGREES = 10.0

FIELDNAMES = (
    "osm_type",
    "osm_id",
    "kind",
    "name",
    "operator",
    "voltage_kv",
    "source",
    "capacity_mw",
    "lat",
    "lon",
)

# `plant:output:electricity` is free text. These are the forms that appear in
# practice; anything else is left blank rather than guessed at, because a
# capacity figure invented from an unparseable string would look reported.
CAPACITY_PATTERN = re.compile(r"^\s*([\d.]+)\s*(gw|mw|kw|w)?\s*$", re.IGNORECASE)
CAPACITY_TO_MW = {"gw": 1000.0, "mw": 1.0, "kw": 0.001, "w": 1e-6, None: 1.0}


def build_query(box: BoundingBox, timeout: int = 300) -> str:
    """Return the Overpass QL for one tile."""
    bbox = box.as_overpass()
    return (
        f"[out:json][timeout:{timeout}];\n"
        "(\n"
        f'  nwr["power"="substation"]["voltage"~"{VOLTAGE_PATTERN}"]{bbox};\n'
        f'  nwr["power"="plant"]{bbox};\n'
        ");\n"
        "out tags center;"
    )


def max_voltage_v(raw: str | None) -> float | None:
    """Return the highest voltage in an OSM ``voltage`` tag, in volts.

    Handles the semicolon lists that multi-level substations carry. Returns
    ``None`` when nothing in the tag parses as a number, which is the honest
    answer for the free-text values that occasionally appear.
    """
    if not raw:
        return None
    values: list[float] = []
    for part in str(raw).split(";"):
        try:
            values.append(float(part.strip()))
        except ValueError:
            continue
    return max(values) if values else None


def capacity_mw(raw: str | None) -> float | None:
    """Return a plant's electrical output in MW, or ``None`` if unparseable."""
    if not raw:
        return None
    match = CAPACITY_PATTERN.match(str(raw))
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = (match.group(2) or "").lower() or None
    # A bare number in this tag is conventionally watts when it is large and
    # megawatts when small; rather than guess, only a unit-bearing value or a
    # plainly small number is trusted.
    if unit is None and value > 10_000:
        return None
    return round(value * CAPACITY_TO_MW[unit], 3)


def position(element: dict[str, Any]) -> tuple[float, float] | None:
    """Return ``(lat, lon)`` for a node, way or relation, or ``None``."""
    if element.get("type") == "node" and "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def normalise(element: dict[str, Any]) -> dict[str, Any] | None:
    """Reduce one Overpass element to a row, or ``None`` to drop it."""
    tags = element.get("tags") or {}
    power = tags.get("power")
    if power not in {"substation", "plant"}:
        return None

    where = position(element)
    if where is None:
        # No coordinate means nothing can be drawn or placed. Dropped and
        # counted by the caller rather than written with a zeroed position.
        return None
    lat, lon = where

    volts = max_voltage_v(tags.get("voltage"))
    # The server-side regex is an optimisation; this is the filter that decides.
    # A substation whose voltage tag is free text cannot be shown to meet the
    # threshold, so it is left out.
    if power == "substation" and (volts is None or volts < MIN_VOLTAGE_V):
        return None

    return {
        "osm_type": element.get("type", ""),
        "osm_id": element.get("id", ""),
        "kind": power,
        "name": tags.get("name", "") or "",
        "operator": tags.get("operator", "") or "",
        "voltage_kv": round(volts / 1000.0, 1) if volts else "",
        "source": tags.get("plant:source", "") or tags.get("generator:source", "") or "",
        "capacity_mw": capacity_mw(tags.get("plant:output:electricity")) or "",
        "lat": fmt_coord(lat),
        "lon": fmt_coord(lon),
    }


def fetch(
    tiles: list[tuple[str, BoundingBox]], *, refresh: bool
) -> tuple[list[dict[str, Any]], int]:
    """Fetch every tile, returning de-duplicated rows and a dropped count."""
    by_key: dict[tuple[str, Any], dict[str, Any]] = {}
    dropped = 0

    for _, (label, box) in iter_progress(tiles, "tiles"):
        cache_key = box.key()
        payload = None if refresh else read_cache(CACHE_NAMESPACE, cache_key)
        if payload is None:
            payload = post_form(
                OVERPASS_MIRRORS,
                {"data": build_query(box)},
                timeout=420,
                label=f"grid {label}",
            )
            write_cache(CACHE_NAMESPACE, cache_key, payload)

        for element in payload.get("elements", []):
            row = normalise(element)
            if row is None:
                if (element.get("tags") or {}).get("power") in {"substation", "plant"}:
                    dropped += 1
                continue
            # Tiles share edges, so an asset on a boundary arrives twice.
            by_key[(row["osm_type"], row["osm_id"])] = row

    rows = sorted(by_key.values(), key=lambda r: (r["kind"], r["osm_type"], str(r["osm_id"])))
    return rows, dropped


def main(argv: list[str] | None = None) -> int:
    """Fetch the grid layer and write it. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tile-degrees", type=float, default=DEFAULT_TILE_DEGREES)
    parser.add_argument("--refresh", action="store_true", help="Ignore cached tiles and refetch.")
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args(argv)

    tiles = us_tiles(args.tile_degrees)
    print(f"Fetching grid infrastructure across {len(tiles)} tiles")

    rows, dropped = fetch(tiles, refresh=args.refresh)
    if not rows:
        raise FetchError(
            "No grid assets returned. A throttled run is not evidence of an "
            "empty grid, so nothing has been written."
        )

    substations = [r for r in rows if r["kind"] == "substation"]
    plants = [r for r in rows if r["kind"] == "plant"]
    written = write_csv(args.out, FIELDNAMES, rows)

    print(f"\nWrote {written} rows to {args.out}")
    print(f"  substations >= {MIN_VOLTAGE_V // 1000} kV  {len(substations)}")
    print(f"  generating plants          {len(plants)}")
    print(f"  with a named operator      {sum(1 for r in rows if r['operator'])}")
    print(f"  plants with a capacity     {sum(1 for r in plants if r['capacity_mw'])}")
    if dropped:
        print(f"  dropped (no position or below threshold) {dropped}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nFetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
