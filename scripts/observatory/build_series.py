#!/usr/bin/env python3
"""Aggregate mapping events into per-region growth series. No network.

This is the step the whole fetch layer exists to make possible: because every
event carries a county, a series for any region - a county, a state, the country
- is a local group-by rather than an API call. Adding a new geography costs
nothing and asks nothing of a volunteer-run server.

What the numbers mean, precisely
--------------------------------
``cumulative_count`` is **the number of data centres OpenStreetMap knew about in
that region at the end of that month**. It rises on creations and falls on
removals, so it is a net figure, not a running total of everything ever mapped.

It is not a count of data centres that existed. It is a count of data centres
that had been *mapped*. The two diverge most in the early years, when the tagging
convention barely existed, and that divergence is disclosed rather than smoothed.

``cumulative_footprint_m2`` uses each facility's *current* footprint, attributed
from the month it was first mapped. A building that was later extended therefore
carries its enlarged area backwards. This is an approximation, made because
OpenStreetMap does not retain per-version areas cheaply, and it is stated here
rather than buried.

Run::

    python scripts/observatory/build_series.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from _common import DATA_DIR, FetchError, fmt_area, read_csv, write_csv

FACILITIES_PATH = DATA_DIR / "facilities.csv"
EVENTS_PATH = DATA_DIR / "events.csv"
SERIES_PATH = DATA_DIR / "region_series.csv"

SERIES_FIELDNAMES = (
    "region_id",
    "period",
    "cumulative_count",
    "net_change",
    "cumulative_footprint_m2",
)

# Events that change whether a facility is on the map at all. Tag and geometry
# edits are real history, and they are kept in events.csv for the change feed,
# but they must not move a count: a mapper correcting a spelling does not build
# or remove a data centre.
PRESENCE_EVENTS = {"creation": 1, "deletion": -1}

NATIONAL_REGION_ID = "national:US"


def _month(date_string: str) -> str:
    """Reduce a date to its ``YYYY-MM`` period."""
    return date_string[:7]


def _regions_of(row: dict[str, str]) -> list[str]:
    """Return every region identifier a row contributes to.

    A single facility belongs to its county, its state and the nation at once;
    the series are built in one pass over the events rather than three.
    """
    regions = [NATIONAL_REGION_ID]
    if row.get("state"):
        regions.append(f"state:{row['state']}")
    if row.get("county_fips"):
        regions.append(f"county:{row['county_fips']}")
    return regions


def build(
    events: list[dict[str, str]], footprints: dict[tuple[str, str], float]
) -> list[dict[str, Any]]:
    """Build cumulative monthly series for every region.

    Args:
        events: Rows from ``events.csv``.
        footprints: Current footprint by ``(osm_type, osm_id)``.

    Returns:
        Series rows sorted by region then period.
    """
    # region -> period -> [net count change, net footprint change]
    deltas: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))

    for event in events:
        direction = PRESENCE_EVENTS.get(event.get("event_kind", ""))
        if direction is None:
            continue
        period = _month(event["event_date"])
        area = footprints.get((event["osm_type"], event["osm_id"]), 0.0)
        for region in _regions_of(event):
            bucket = deltas[region][period]
            bucket[0] += direction
            bucket[1] += direction * area

    rows: list[dict[str, Any]] = []
    for region, periods in deltas.items():
        running_count = 0.0
        running_area = 0.0
        # Every month between the first and last event is emitted, including the
        # quiet ones. A chart that skipped empty months would compress time and
        # make a pause look like continuous growth.
        ordered = sorted(periods)
        for period in _month_range(ordered[0], ordered[-1]):
            change, area_change = periods.get(period, [0.0, 0.0])
            running_count += change
            running_area += area_change
            rows.append(
                {
                    "region_id": region,
                    "period": period,
                    "cumulative_count": int(running_count),
                    "net_change": int(change),
                    "cumulative_footprint_m2": fmt_area(max(running_area, 0.0)),
                }
            )

    rows.sort(key=lambda r: (str(r["region_id"]), str(r["period"])))
    return rows


def _month_range(first: str, last: str) -> list[str]:
    """Return every ``YYYY-MM`` period from ``first`` to ``last`` inclusive."""
    year, month = int(first[:4]), int(first[5:7])
    end_year, end_month = int(last[:4]), int(last[5:7])
    periods: list[str] = []
    while (year, month) <= (end_year, end_month):
        periods.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return periods


def main(argv: list[str] | None = None) -> int:
    """Build the series file. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facilities", type=Path, default=FACILITIES_PATH)
    parser.add_argument("--events", type=Path, default=EVENTS_PATH)
    parser.add_argument("--out", type=Path, default=SERIES_PATH)
    args = parser.parse_args(argv)

    facilities = read_csv(args.facilities)
    events = read_csv(args.events)
    if not events:
        raise FetchError(
            f"{args.events} is empty. Run fetch_osm_history.py before building series."
        )
    if not any(e.get("county_fips") for e in events):
        raise FetchError(
            "No event carries a county. Run assign_regions.py before building "
            "series, or every series would collapse into the national one."
        )

    footprints = {
        (f["osm_type"], f["osm_id"]): float(f.get("footprint_m2") or 0.0) for f in facilities
    }

    rows = build(events, footprints)
    written = write_csv(args.out, SERIES_FIELDNAMES, rows)

    regions = {str(r["region_id"]) for r in rows}
    counties = sum(1 for r in regions if r.startswith("county:"))
    states = sum(1 for r in regions if r.startswith("state:"))
    national = [r for r in rows if r["region_id"] == NATIONAL_REGION_ID]

    print(f"Wrote {written} series rows to {args.out}")
    print(f"  {counties} counties, {states} states, 1 national")
    if national:
        print(f"  national series {national[0]['period']} to {national[-1]['period']}")
        print("\n  National, mapped data centres at year end:")
        for row in national:
            if row["period"].endswith("-12") or row is national[-1]:
                print(f"    {row['period']}  {row['cumulative_count']:>5}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nBuild failed: {exc}", file=sys.stderr)
        sys.exit(1)
