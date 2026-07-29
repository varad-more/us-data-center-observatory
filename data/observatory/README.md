# Observatory dataset

Committed CSVs describing US data centres: where they are, how big they are,
when the map first recorded them, and what share of national electricity and
water their footprint accounts for.

These files are the canonical data. The published site is built from them, and
the JSON under `apps/web/public/data` is derived — regenerate it, never edit it.

**The `git diff` on this directory is the change log.** Every writer sorts rows
on a stable key and formats numbers to fixed precision, so re-running the
pipeline when nothing has changed upstream produces byte-identical files. A diff
here always means real movement.

## Files

| File | Grain | What it is |
|---|---|---|
| `facilities.csv` | one row per OSM element | Every data centre OpenStreetMap records in a US county: identity, coordinates, operator, building footprint, county, and the date the map first recorded it. |
| `events.csv` | one row per edit | Creations, removals and edits from OpenStreetMap's history, with coordinates and county. The time axis. |
| `regions.csv` | one row per county and state | Facility counts, total footprint, and the allocated share of national electricity and water. |
| `region_series.csv` | region × month | Cumulative facility count and footprint per region per month. |
| `national_energy.csv` | one row per year and scenario | LBNL's published US data-centre electricity and water totals, historical and projected. |
| `grid.csv` | one row per OSM element | Transmission substations at 69 kV and above, and generating plants: identity, coordinates, highest voltage, fuel source and rated capacity where a mapper recorded them. Context for where a large load can physically go. |
| `grid_regions.csv` | one row per county and state | Substation counts split at 230 kV, the highest voltage present, and generating capacity where mappers recorded it. The grid context for a siting question. |
| `poll_log.csv` | one row per poll | What each refresh changed. |

`.cache/` holds raw per-tile API payloads so an interrupted fetch resumes rather
than restarts. It is not committed.

## Regenerating

```bash
python scripts/observatory/poll.py          # everything, then a diff summary
python scripts/observatory/poll.py --skip-fetch   # rebuild derived files only
```

Stages can also be run individually; see each script's docstring. County
boundaries come from `scripts/observatory/fetch_county_boundaries.py` and only
need refetching when the Census publishes a new vintage.

## What these numbers mean

Three distinctions do the work, and collapsing any of them produces a figure
that looks right and is not.

**A count is a count of what has been mapped.** OpenStreetMap is built by
volunteers. A county with no facilities has not been shown to have none; it may
have no mappers. Completeness is unknown and cannot be measured, because no
authoritative count of US data centres exists to check against.

**A date is when the map recorded a facility, not when it was built.**
OpenStreetMap carries no construction dates — `start_date` coverage is zero. One
Loudoun County building was drawn in 2010 and only tagged as a data centre in
2016. Nothing here asserts a build date, and the near-total absence of records
before 2017 reflects the adoption of the `telecom=data_center` tag rather than an
empty country. For the same reason a removal is written as "removed from
OpenStreetMap": a mapper retagging a building is indistinguishable from one
being demolished.

**A megawatt figure is a share, not a meter reading.** Nobody meters these
buildings. LBNL's reported national totals are allocated across mapped
facilities by footprint, so the shares re-sum to the published total by
construction — but the whole national total is spread over only the facilities
that have been mapped, so every per-facility figure is an upper bound. Footprint
is a proxy for capacity and an imperfect one: this method gives Virginia
2,255 MW where Virginia's JLARC study puts Northern Virginia alone near
4,100 MW.

## Sources

- Facility locations, footprints and operators — OpenStreetMap contributors, via
  the Overpass API. Licensed ODbL.
- Edit history — the [ohsome API](https://api.ohsome.org), HeiGIT, over the same
  OpenStreetMap data.
- County boundaries — US Census Bureau TIGERweb. Public domain.
- National electricity and water — Lawrence Berkeley National Laboratory,
  *United States Data Center Energy Usage Report* (2024) and *2025 Update*.
