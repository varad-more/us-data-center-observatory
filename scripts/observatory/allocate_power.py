#!/usr/bin/env python3
"""Allocate national data-centre power and water across mapped facilities.

No public source meters an individual data centre. What does exist is a credible
national total - Lawrence Berkeley National Laboratory puts US data-centre
electricity at 192 TWh for 2024 and direct water consumption at 17.4 billion
gallons for 2023 - and a building footprint for most mapped facilities. This
script distributes the former across the latter, weighted by floor area.

Why weight by footprint
-----------------------
Because size varies enormously and a flat per-facility figure would be wrong by
more than an order of magnitude. Measured in Loudoun County, footprints run from
a 12,515 m2 median to a 426,398 m2 campus - a 34-fold spread. Area is a crude
proxy for capacity, but it is a vastly better one than facility count.

What this figure is, and is not
-------------------------------
It is **a facility's share of a reported national total**, and the shares sum to
that total by construction. It is not a meter reading, and it is not a
measurement of that building.

One assumption dominates everything else and cannot be verified: allocating the
whole national total across only the *mapped* stock assumes OpenStreetMap knows
about every data centre in the country. It does not. Every facility missing from
the map has its consumption silently redistributed onto the ones that are
present, so **every per-facility figure here is an upper bound**. The size of
that error is unknown, because no authoritative count of US data centres exists
to compare against. This is stated in the output, in the API payloads and on the
page - never quietly assumed away.

Run::

    python scripts/observatory/allocate_power.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import DATA_DIR, FetchError, read_csv, write_csv

FACILITIES_PATH = DATA_DIR / "facilities.csv"
REGIONS_PATH = DATA_DIR / "regions.csv"
NATIONAL_PATH = DATA_DIR / "national_energy.csv"
OUT_PATH = DATA_DIR / "regions.csv"

HOURS_PER_YEAR = 8760.0
DAYS_PER_YEAR = 365.0

REGION_FIELDNAMES = (
    "region_id",
    "region_kind",
    "name",
    "state",
    "fips",
    "facility_count",
    "footprint_m2",
    "share_of_footprint",
    "est_mw",
    "est_gal_per_day",
)


def latest_historical(rows: list[dict[str, str]], column: str) -> tuple[int, float]:
    """Return the most recent published historical value for ``column``.

    Electricity and water are published on different clocks - the 2025 update
    carries electricity through 2024 while water still rests on the 2024 report's
    2023 figure. Each is therefore resolved independently and carries its own
    year, rather than being forced onto a shared one.

    Raises:
        FetchError: When no historical row carries the column.
    """
    candidates = [
        (int(r["year"]), float(r[column]))
        for r in rows
        if r.get("series_kind") == "historical" and r.get(column)
    ]
    if not candidates:
        raise FetchError(f"national_energy.csv has no historical value for {column}")
    return max(candidates, key=lambda pair: pair[0])


def main(argv: list[str] | None = None) -> int:
    """Allocate national totals across regions. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facilities", type=Path, default=FACILITIES_PATH)
    parser.add_argument("--regions", type=Path, default=REGIONS_PATH)
    parser.add_argument("--national", type=Path, default=NATIONAL_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    facilities = read_csv(args.facilities)
    regions = read_csv(args.regions)
    national = read_csv(args.national)
    if not facilities or not regions:
        raise FetchError(
            "facilities.csv and regions.csv must both be populated. Run "
            "fetch_osm_snapshot.py and assign_regions.py first."
        )

    electricity_year, twh = latest_historical(national, "electricity_twh")
    water_year, bgal = latest_historical(national, "water_bgal")

    # A TWh over a year is an average power. Peak draw is higher and Helios has
    # no basis to estimate it, so the published figure is explicitly an average.
    national_mw = twh * 1e12 / HOURS_PER_YEAR / 1e6
    national_gal_per_day = bgal * 1e9 / DAYS_PER_YEAR

    total_footprint = sum(float(f.get("footprint_m2") or 0.0) for f in facilities)
    if total_footprint <= 0:
        raise FetchError(
            "Total mapped footprint is zero, so there is no weight to allocate by. "
            "Check that fetch_osm_snapshot.py recorded building geometry."
        )

    with_footprint = sum(1 for f in facilities if float(f.get("footprint_m2") or 0.0) > 0)

    allocated_mw = 0.0
    allocated_gal = 0.0
    for region in regions:
        area = float(region.get("footprint_m2") or 0.0)
        share = area / total_footprint
        # State and county rows both exist, and both cover the same facilities.
        # Only one family may be counted when checking conservation, or the sum
        # would come to twice the national total.
        region["share_of_footprint"] = f"{share:.8f}"
        region["est_mw"] = f"{share * national_mw:.2f}"
        region["est_gal_per_day"] = f"{share * national_gal_per_day:.0f}"
        if region.get("region_kind") == "state":
            allocated_mw += share * national_mw
            allocated_gal += share * national_gal_per_day

    written = write_csv(args.out, REGION_FIELDNAMES, regions)

    print(f"Allocated national totals across {len(facilities)} facilities")
    print(f"  electricity   {twh:.0f} TWh ({electricity_year}) = {national_mw:,.0f} MW average")
    print(
        f"  water         {bgal:.1f} bn gal ({water_year}) "
        f"= {national_gal_per_day:,.0f} gal/day"
    )
    print(f"  footprint     {total_footprint / 1e6:.2f} km2 across {with_footprint} facilities")
    print(f"  wrote         {written} regions to {args.out}")

    # Conservation check. States partition the mapped stock, so their allocations
    # must re-sum to the national total; drift means the weights are wrong.
    drift = abs(allocated_mw - national_mw) / national_mw if national_mw else 0.0
    print(f"\n  state allocations sum to {allocated_mw:,.0f} MW of {national_mw:,.0f} MW")
    if drift > 0.01:
        print(
            f"  NOTE: {drift * 100:.1f}% of the allocation is unattributed - facilities "
            "whose coordinates fell outside every county boundary."
        )
    print(
        "\n  Every per-facility figure is an upper bound: the whole national total is\n"
        "  spread across mapped facilities only, so unmapped ones have their share\n"
        "  attributed to those that are visible."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nAllocation failed: {exc}", file=sys.stderr)
        sys.exit(1)
