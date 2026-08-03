#!/usr/bin/env python3
"""Summarise the grid, county by county, entirely offline.

The grid layer arrived as a map layer and nothing else read it. This turns it
into an answer to the question that actually decides where a large load can go:
*what is the electrical capability of this county?*

Two figures do most of that work, and they are deliberately separate:

**Substations by voltage class.** Counts alone would put a county with forty
69 kV distribution-adjacent yards above one with a single 500 kV bulk
substation, which is backwards for a load measured in hundreds of megawatts.
The classes are reported separately and the highest voltage present is carried
on its own, because that is the number a siting decision turns on.

**Generating capacity.** Only where a mapper recorded it. The count of plants
whose capacity is *unknown* is carried beside the total, so a county whose
generation is simply untagged cannot be read as a county with none.

Written to its own file rather than added to ``regions.csv``. The grid is
context for the facility data, not part of it, and a fetch that fails or a
county that cannot be matched must not be able to disturb the counts and
allocations that the rest of the site rests on.

Run::

    python scripts/observatory/assign_grid_regions.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Any

from _common import DATA_DIR, FetchError, read_csv, state_name, write_csv
from assign_regions import BOUNDARIES_PATH, CountyIndex, _assign
from fetch_grid import FIELDNAMES as GRID_FIELDNAMES

GRID_PATH = DATA_DIR / "grid.csv"
OUT_PATH = DATA_DIR / "grid_regions.csv"

# Bulk transmission. A facility drawing hundreds of megawatts connects at this
# level or above; below it the substation is serving a town, not a campus.
BULK_KV = 230.0

FIELDNAMES = (
    "region_id",
    "region_kind",
    "name",
    "state",
    "fips",
    "substation_count",
    "bulk_substation_count",
    "max_voltage_kv",
    "plant_count",
    "plant_capacity_mw",
    "plants_without_capacity",
)


def _blank_totals() -> dict[str, Any]:
    """Return a zeroed accumulator for one region."""
    return {
        "substation_count": 0,
        "bulk_substation_count": 0,
        "max_voltage_kv": 0.0,
        "plant_count": 0,
        "plant_capacity_mw": 0.0,
        "plants_without_capacity": 0,
    }


def _accumulate(totals: dict[str, Any], row: dict[str, str]) -> None:
    """Fold one grid asset into a region's running totals."""
    if row.get("kind") == "substation":
        totals["substation_count"] += 1
        try:
            kv = float(row.get("voltage_kv") or 0.0)
        except ValueError:
            kv = 0.0
        if kv >= BULK_KV:
            totals["bulk_substation_count"] += 1
        totals["max_voltage_kv"] = max(totals["max_voltage_kv"], kv)
        return

    totals["plant_count"] += 1
    raw = row.get("capacity_mw") or ""
    if not raw:
        # Counted rather than treated as zero. A plant with no capacity tag is
        # an unknown, and summing it as nought would understate the county while
        # looking like a measurement of it.
        totals["plants_without_capacity"] += 1
        return
    try:
        totals["plant_capacity_mw"] += float(raw)
    except ValueError:
        totals["plants_without_capacity"] += 1


def build(grid: list[dict[str, str]], index: CountyIndex) -> list[dict[str, Any]]:
    """Aggregate grid assets into county and state rows."""
    counties: dict[str, dict[str, Any]] = defaultdict(_blank_totals)
    states: dict[str, dict[str, Any]] = defaultdict(_blank_totals)
    names = {p["fips"]: p for p in index.properties}

    for row in grid:
        fips = row.get("county_fips") or ""
        state = row.get("state") or ""
        if not fips:
            continue
        _accumulate(counties[fips], row)
        if state:
            _accumulate(states[state], row)

    rows: list[dict[str, Any]] = []
    for fips, totals in counties.items():
        meta = names.get(fips)
        if meta is None:
            continue
        rows.append(
            {
                "region_id": f"county:{fips}",
                "region_kind": "county",
                "name": meta["name"],
                "state": meta["state"],
                "fips": fips,
                **totals,
            }
        )
    for state, totals in states.items():
        rows.append(
            {
                "region_id": f"state:{state}",
                "region_kind": "state",
                "name": state_name(state),
                "state": state,
                "fips": "",
                **totals,
            }
        )

    for row in rows:
        row["max_voltage_kv"] = f"{float(row['max_voltage_kv']):.1f}"
        row["plant_capacity_mw"] = f"{float(row['plant_capacity_mw']):.1f}"

    rows.sort(key=lambda r: (r["region_kind"], str(r["region_id"])))
    return rows


def main(argv: list[str] | None = None) -> int:
    """Assign grid assets to counties and summarise. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", default=GRID_PATH)
    parser.add_argument("--out", default=OUT_PATH)
    args = parser.parse_args(argv)

    grid = read_csv(args.grid)
    if not grid:
        raise FetchError(
            f"No grid data at {args.grid}. Run " "`python scripts/observatory/fetch_grid.py` first."
        )

    index = CountyIndex(BOUNDARIES_PATH)
    print(f"Placing {len(grid)} grid assets against {len(index.geometries)} counties")
    _assign(grid, index, "grid")

    # Written back, not just used and dropped. The assignment is the only record
    # of which of these assets are in the United States - the fetch boxes reach
    # into Mexico and Canada - and every downstream consumer needs that answer.
    # Keeping it in memory meant the county totals were right while the
    # published point layer and the headline count were quietly national plus
    # 1,300 substations in Sonora and Ontario.
    write_csv(args.grid, GRID_FIELDNAMES, grid)

    rows = build(grid, index)
    counties = [r for r in rows if r["region_kind"] == "county"]
    states = [r for r in rows if r["region_kind"] == "state"]
    written = write_csv(args.out, FIELDNAMES, rows)

    top = max(counties, key=lambda r: r["bulk_substation_count"], default=None)
    print(f"\nWrote {written} rows to {args.out}")
    print(f"  counties with grid assets  {len(counties)}")
    print(f"  states                     {len(states)}")
    if top:
        print(
            f"  most bulk substations      {top['name']}, {top['state']} "
            f"({top['bulk_substation_count']} at {BULK_KV:.0f} kV+)"
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nFailed: {exc}", file=sys.stderr)
        sys.exit(1)
