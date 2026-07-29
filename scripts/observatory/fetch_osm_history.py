#!/usr/bin/env python3
"""Fetch the edit history of US data centres from the ohsome API.

This is the time axis of the whole project, and it must be read for exactly what
it is. Each row records **when OpenStreetMap changed**, not when concrete was
poured. A creation event is a mapper adding a building; the building may have
stood for a decade already. This file therefore never emits a "built" date, and
every consumer downstream labels the resulting series ``observed``.

Two consequences follow, and both are load-bearing:

*The early years are an artefact.* Almost nothing appears before 2017, because
``telecom=data_center`` was not in common use, not because the United States had
no data centres. Any chart drawn from this must say so.

*A deletion is not a demolition.* ohsome reports a deletion when an element stops
matching the filter. That happens when a building is genuinely removed from the
map, and equally when a mapper retags it - ``building=data_center`` becoming
``building=yes`` looks identical here. The honest phrasing, used everywhere
downstream, is "removed from OpenStreetMap".

Run::

    python scripts/observatory/fetch_osm_history.py
    python scripts/observatory/fetch_osm_history.py --tile-degrees 3 --refresh
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from _common import (
    DATA_DIR,
    OHSOME_BASE,
    OHSOME_FILTER,
    BoundingBox,
    FetchError,
    fmt_coord,
    get_json,
    post_form,
    read_cache,
    read_csv,
    us_tiles,
    write_cache,
    write_csv,
)

OUT_PATH = DATA_DIR / "events.csv"
FACILITIES_PATH = DATA_DIR / "facilities.csv"

# Written only when a full backfill has covered every facility-bearing tile.
# Its absence forces a full run, which is the safe default: asking for too much
# history costs time, asking for too little loses years without saying so.
COMPLETE_MARKER = DATA_DIR / ".cache" / "osm-history" / "BACKFILL_COMPLETE"
CACHE_NAMESPACE = "osm-history"
DEFAULT_TILE_DEGREES = 5.0

# OpenStreetMap's ODbL-compliant history begins in 2007, but the data-centre
# tagging conventions post-date that by a decade. Starting at the beginning is
# deliberate: the flat early stretch is evidence about the tag, and cropping it
# would hide the very artefact the charts have to disclose.
HISTORY_START = "2012-01-01"

# Days of already-fetched history an incremental run re-requests. ohsome's
# extract trails real time, so the newest days of any run may have been
# incomplete when it happened; re-asking for them is cheap and closes the gap.
OVERLAP_DAYS = 14

FIELDNAMES = (
    "osm_type",
    "osm_id",
    "event_date",
    "event_kind",
    "lat",
    "lon",
    "county_fips",
    "state",
)

# One contribution can carry several flags at once - a mapper who moves a
# building and renames it produces both. Rows are one-per-contribution, so a
# single kind is chosen by this precedence: existence changes outrank edits.
KIND_PRECEDENCE: tuple[tuple[str, str], ...] = (
    ("@creation", "creation"),
    ("@deletion", "deletion"),
    ("@tagChange", "tag_change"),
    ("@geometryChange", "geometry_change"),
)


def temporal_extent() -> tuple[str, str]:
    """Return ohsome's available history window as ``(from, to)`` timestamps.

    The end of the window trails real time by days to weeks. Requesting beyond
    it is a hard 404, so the window is read rather than assumed.
    """
    payload = get_json(f"{OHSOME_BASE}/metadata", timeout=60.0)
    extent = payload["extractRegion"]["temporalExtent"]
    return str(extent["fromTimestamp"]), str(extent["toTimestamp"])


def _to_date(timestamp: str) -> str:
    """Reduce an ISO timestamp to a calendar date."""
    return timestamp[:10]


def _split_osm_id(value: str) -> tuple[str, str]:
    """Split ohsome's ``way/123`` identifier into its type and numeric id."""
    kind, _, identifier = value.partition("/")
    return kind, identifier


def _kind_of(properties: dict[str, Any]) -> str | None:
    """Return the single event kind for a contribution, or ``None`` if unknown."""
    for flag, kind in KIND_PRECEDENCE:
        if properties.get(flag):
            return kind
    return None


def _occupied_tiles(
    tiles: list[tuple[str, BoundingBox]], facilities: list[dict[str, str]]
) -> set[str]:
    """Return the labels of tiles containing at least one current facility.

    Roughly half the grid is open ocean and empty wilderness. Those tiles are
    still worth asking about - a facility could have been mapped there and since
    removed - but they are not what the history is *for*, and a run that has
    covered every occupied tile has covered every facility on the map.
    """
    points = []
    for row in facilities:
        try:
            points.append((float(row["lon"]), float(row["lat"])))
        except (KeyError, ValueError):
            continue
    occupied = set()
    for label, box in tiles:
        for lon, lat in points:
            if box.west <= lon <= box.east and box.south <= lat <= box.north:
                occupied.add(label)
                break
    return occupied


def fetch(
    tile_degrees: float,
    *,
    refresh: bool,
    start: str,
    end: str,
    budget: float,
    facilities: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Fetch contributions for every tile and return de-duplicated event rows.

    ohsome is a shared research service and a full backfill takes well over an
    hour. ``budget`` caps how long this call spends fetching *new* tiles; cached
    tiles are always replayed, so successive runs make progress and the caller
    can tell whether coverage is complete.

    Tiles holding current facilities are fetched first, so a budgeted run buys
    the most history per second spent.

    Returns:
        A tuple of (event rows, occupied tiles still missing, empty tiles still
        missing).
    """
    tiles = us_tiles(tile_degrees)
    occupied = _occupied_tiles(tiles, facilities)
    # Occupied first: a partial run should be missing empty ocean, not Loudoun.
    tiles.sort(key=lambda pair: pair[0] not in occupied)
    print(
        f"Fetching {len(tiles)} tiles of edit history from ohsome ({start} to {end}); "
        f"{len(occupied)} hold facilities."
    )

    # Keyed by element + timestamp + kind so overlapping tile edges cannot record
    # the same edit twice.
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    # A deletion arrives with no geometry, and the tile that holds the element's
    # earlier edits may not have been read yet, so they are resolved at the end
    # against every coordinate seen anywhere.
    last_known: dict[tuple[str, str], tuple[float, float]] = {}
    pending_deletions: list[tuple[str, str, str]] = []
    unknown = 0
    missing_occupied = 0
    missing_empty = 0
    started = time.monotonic()
    for index, (label, box) in enumerate(tiles, start=1):
        # The window is part of the cache identity. Without it an incremental
        # run would be served the full backfill's payload, or worse, a later
        # full run would be served a narrow incremental one and silently lose
        # a decade of history.
        cache_key = f"{box.key()}__{start[:10]}__{end[:10]}"
        cached = None if refresh else read_cache(CACHE_NAMESPACE, cache_key)
        if cached is None:
            if budget and time.monotonic() - started > budget:
                if label in occupied:
                    missing_occupied += 1
                else:
                    missing_empty += 1
                continue
            payload = post_form(
                [f"{OHSOME_BASE}/contributions/centroid"],
                {
                    "bboxes": box.as_ohsome(),
                    "time": f"{start},{end}",
                    "filter": OHSOME_FILTER,
                    # `contributionTypes` is what makes ohsome emit the
                    # @creation / @deletion / @tagChange flags. Without it the
                    # response still carries every contribution, but with no way
                    # to tell what kind it was - and every row is silently
                    # unusable. Requesting only `tags` produced exactly that.
                    "properties": "tags,contributionTypes",
                },
                label=f"tile {label}",
            )
            write_cache(CACHE_NAMESPACE, cache_key, payload)
            source = "fetched"
        else:
            payload = cached
            source = "cached"

        features = payload.get("features") or []
        added = 0
        for feature in features:
            properties = feature.get("properties") or {}
            kind = _kind_of(properties)
            if kind is None:
                unknown += 1
                continue
            osm_type, osm_id = _split_osm_id(str(properties.get("@osmId") or ""))
            if not osm_type or not osm_id:
                unknown += 1
                continue
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            timestamp = str(properties.get("@timestamp") or "")

            if len(coordinates) == 2:
                # Remember where this element was, so a later deletion of it can
                # still be placed in a county.
                last_known[(osm_type, osm_id)] = (
                    float(coordinates[0]),
                    float(coordinates[1]),
                )
            elif kind == "deletion":
                # ohsome returns no centroid for a deletion: by then the element
                # is gone and has no geometry to report. Dropping these for want
                # of a coordinate is how every removal disappeared from an
                # earlier version, leaving counts that could only ever rise.
                pending_deletions.append((osm_type, osm_id, timestamp))
                added += 1
                continue
            else:
                unknown += 1
                continue

            key = (osm_type, osm_id, timestamp, kind)
            if key in by_key:
                continue
            by_key[key] = {
                "osm_type": osm_type,
                "osm_id": osm_id,
                "event_date": _to_date(timestamp),
                "event_kind": kind,
                "lat": fmt_coord(float(coordinates[1])),
                "lon": fmt_coord(float(coordinates[0])),
                "county_fips": "",
                "state": "",
            }
            added += 1
        print(
            f"  [{index:>3}/{len(tiles)}] {label:<16} {len(features):>5} contributions, "
            f"+{added} new ({source})"
        )

    # Place the deletions now that every tile has contributed whatever it knew
    # about where these elements used to be.
    unplaced = 0
    for osm_type, osm_id, timestamp in pending_deletions:
        position = last_known.get((osm_type, osm_id))
        key = (osm_type, osm_id, timestamp, "deletion")
        if key in by_key:
            continue
        by_key[key] = {
            "osm_type": osm_type,
            "osm_id": osm_id,
            "event_date": _to_date(timestamp),
            "event_kind": "deletion",
            # An element deleted before any edit this window saw has no known
            # position. The removal is still recorded - it is real, and dropping
            # it would inflate the count - but it cannot be attributed to a
            # county, and assign_regions will leave its region columns empty.
            "lat": fmt_coord(position[1]) if position else "",
            "lon": fmt_coord(position[0]) if position else "",
            "county_fips": "",
            "state": "",
        }
        if position is None:
            unplaced += 1
    if unplaced:
        print(f"  {unplaced} removals could not be placed: no earlier edit recorded a position")

    # A handful of unusable contributions is normal; a majority means the request
    # itself is wrong. This exact check would have caught asking ohsome for
    # `properties=tags` without `contributionTypes`, which returns every
    # contribution stripped of the flag that says what it was - producing an
    # empty history that looks like a country with no data centres.
    seen = len(by_key) + unknown
    if unknown and seen and unknown / seen > 0.25:
        raise FetchError(
            f"{unknown} of {seen} contributions carried no usable kind. That is a "
            "malformed request, not sparse data - check that `properties` includes "
            "`contributionTypes`. Refusing to write a history built from the rest."
        )
    if unknown:
        print(f"  skipped {unknown} contributions with no usable id, kind or centroid")

    return (
        sorted(
            by_key.values(),
            key=lambda r: (
                str(r["event_date"]),
                str(r["osm_type"]),
                int(r["osm_id"]),
                str(r["event_kind"]),
            ),
        ),
        missing_occupied,
        missing_empty,
    )


def main(argv: list[str] | None = None) -> int:
    """Fetch history and write ``events.csv``. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="Destination CSV")
    parser.add_argument(
        "--tile-degrees", type=float, default=DEFAULT_TILE_DEGREES, help="Tile size in degrees"
    )
    parser.add_argument("--refresh", action="store_true", help="Ignore cached tiles")
    parser.add_argument(
        "--since",
        default=None,
        help=(
            "Fetch only contributions on or after this date (YYYY-MM-DD) and merge "
            "them into the existing file. Defaults to resuming from the last date "
            "already recorded; use --full for a complete backfill."
        ),
    )
    parser.add_argument(
        "--full", action="store_true", help="Refetch the whole history rather than resuming"
    )
    parser.add_argument(
        "--time-budget",
        type=float,
        default=0.0,
        help=(
            "Seconds to spend fetching new tiles before stopping (0 = no limit). "
            "Progress is cached, so re-running continues where this left off."
        ),
    )
    args = parser.parse_args(argv)

    _available_from, available_to = temporal_extent()
    existing = read_csv(args.out)

    # The backfill is expensive and only has to happen once. Later polls ask for
    # the tail, then merge. The overlap window re-requests the last few days on
    # purpose: ohsome's extract lags real time, so the most recent days of a
    # previous run may have been incomplete when it ran.
    #
    # Switching to incremental is gated on a marker written only when a full
    # backfill actually completed - never on events.csv merely existing. An
    # earlier version keyed off the file, and a partial 46-row file was enough
    # to put every later run into incremental mode, so the backfill could never
    # finish: each run asked for the last five weeks and reported the remaining
    # fourteen years as already covered.
    if args.full or not existing or not COMPLETE_MARKER.exists():
        start = HISTORY_START
        mode = "full backfill"
    elif args.since:
        start = args.since
        mode = f"incremental from {args.since}"
    else:
        last = max(str(r["event_date"]) for r in existing)
        start = (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat()
        mode = f"incremental from {start} (last recorded {last})"
    print(f"Mode: {mode}")

    rows, missing_occupied, missing_empty = fetch(
        args.tile_degrees,
        refresh=args.refresh,
        start=start,
        end=available_to,
        budget=args.time_budget,
        facilities=read_csv(FACILITIES_PATH),
    )

    if missing_occupied:
        # Deliberately not written. A history file assembled from part of the
        # country would understate every national and state figure derived from
        # it, and would look exactly like a complete one. The cache holds the
        # progress, so re-running resumes rather than restarts.
        print(
            f"\nStopped with {missing_occupied} facility-bearing tiles still unfetched.\n"
            f"{args.out} was NOT written - a partial history would understate every\n"
            "series built from it. Re-run this command to continue; cached tiles\n"
            "are replayed instantly."
        )
        return 0

    if not rows and not existing:
        raise FetchError(
            "ohsome returned no contributions for any tile. Refusing to write an "
            "empty history: that would erase the entire time axis."
        )

    # Merge onto what is already recorded. Existing rows win on the region
    # columns, which assign_regions.py filled in; the fetch never blanks them.
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {
        (r["osm_type"], r["osm_id"], r["event_date"], r["event_kind"]): dict(r) for r in existing
    }
    added = 0
    for row in rows:
        key = (row["osm_type"], row["osm_id"], row["event_date"], row["event_kind"])
        prior = merged.get(key)
        if prior is None:
            merged[key] = row
            added += 1
        else:
            row["county_fips"] = prior.get("county_fips", "")
            row["state"] = prior.get("state", "")
            merged[key] = row

    rows = sorted(
        merged.values(),
        key=lambda r: (
            str(r["event_date"]),
            str(r["osm_type"]),
            int(r["osm_id"]),
            str(r["event_kind"]),
        ),
    )

    written = write_csv(args.out, FIELDNAMES, rows)
    if start == HISTORY_START:
        # Only a run that asked for the whole window and got every
        # facility-bearing tile may license later incremental runs.
        COMPLETE_MARKER.parent.mkdir(parents=True, exist_ok=True)
        COMPLETE_MARKER.write_text(
            f"Full backfill {HISTORY_START} to {available_to} completed.\n", encoding="utf-8"
        )

    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["event_kind"])] = counts.get(str(row["event_kind"]), 0) + 1

    print(f"\nWrote {written} events to {args.out} ({added} new this run)")
    if missing_empty:
        # Stated rather than hidden. These tiles hold no facility today, so the
        # only history they could contain is of one mapped and since removed.
        print(
            f"  NOTE: {missing_empty} tiles with no current facility were not checked. "
            "A data\n        centre mapped there and since removed would be missing "
            "from this history."
        )
    for kind in ("creation", "deletion", "tag_change", "geometry_change"):
        if kind in counts:
            print(f"  {kind:<16} {counts[kind]}")
    print(f"  date range      {rows[0]['event_date']} to {rows[-1]['event_date']}")
    print(
        f"  net present     {counts.get('creation', 0) - counts.get('deletion', 0)} "
        "(creations minus removals; a removal may be a retag, not a demolition)"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FetchError as exc:
        print(f"\nFetch failed: {exc}", file=sys.stderr)
        sys.exit(1)
