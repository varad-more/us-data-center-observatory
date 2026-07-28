#!/usr/bin/env python3
"""Refresh the observatory dataset, then report what actually changed.

This is the one command to run before deploying. It walks the stages in order,
and finishes by diffing the new facility set against the old one so the answer
to "what moved since last time?" is on screen rather than buried in a CSV.

Because the CSVs are committed and written deterministically, ``git diff`` after
this run is itself a truthful change log: a diff means real movement upstream,
never a re-serialisation artefact.

Stages::

    fetch_osm_snapshot   what exists now        (Overpass, ~2 min)
    fetch_osm_history    when it was mapped     (ohsome, slow, resumable)
    assign_regions       place it in a county   (offline)
    build_series         growth per region      (offline)
    allocate_power       share of national load (offline)
    build_site_data      JSON for the site      (offline)

The history stage is the slow one and it is allowed to be incomplete: it caches
per tile and resumes, and refuses to write a partial file. Everything else
completes in seconds.

Run::

    python scripts/observatory/poll.py
    python scripts/observatory/poll.py --skip-history      # offline rebuild
    python scripts/observatory/poll.py --history-budget 600
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from _common import DATA_DIR, read_csv, write_csv

HERE = Path(__file__).resolve().parent
FACILITIES_PATH = DATA_DIR / "facilities.csv"
POLL_LOG_PATH = DATA_DIR / "poll_log.csv"

POLL_FIELDNAMES = (
    "polled_at",
    "facilities_before",
    "facilities_after",
    "appeared",
    "disappeared",
    "states_touched",
)


def _snapshot_ids() -> dict[tuple[str, str], dict[str, str]]:
    """Return the current facility set keyed by OSM identifier."""
    return {(r["osm_type"], r["osm_id"]): r for r in read_csv(FACILITIES_PATH)}


def _run(script: str, extra: list[str] | None = None) -> bool:
    """Run one stage. Returns True when it succeeded."""
    print(f"\n{'=' * 68}\n== {script}\n{'=' * 68}")
    result = subprocess.run(
        [sys.executable, str(HERE / script), *(extra or [])],
        check=False,
    )
    if result.returncode != 0:
        print(f"\n!! {script} failed with exit code {result.returncode}")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """Run every stage and report the diff. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Skip the slow ohsome backfill and rebuild from what is already cached",
    )
    parser.add_argument(
        "--history-budget",
        type=float,
        default=0.0,
        help="Seconds to spend fetching new history tiles (0 = no limit)",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Do not touch the network at all; rebuild derived files from the CSVs",
    )
    args = parser.parse_args(argv)

    before = _snapshot_ids()
    print(f"Starting poll. {len(before)} facilities currently recorded.")

    stages: list[tuple[str, list[str]]] = []
    if not args.skip_fetch:
        stages.append(("fetch_osm_snapshot.py", []))
        if not args.skip_history:
            budget = ["--time-budget", str(args.history_budget)] if args.history_budget else []
            stages.append(("fetch_osm_history.py", budget))
    stages.append(("assign_regions.py", []))
    stages.append(("build_series.py", []))
    stages.append(("allocate_power.py", []))
    stages.append(("build_site_data.py", []))

    failed: list[str] = []
    for script, extra in stages:
        if not _run(script, extra):
            failed.append(script)
            # build_series is expected to fail until the history backfill has
            # completed at least once. That is not a reason to abandon the rest.
            if script not in {"build_series.py", "fetch_osm_history.py"}:
                break

    after = _snapshot_ids()
    appeared = sorted(set(after) - set(before))
    disappeared = sorted(set(before) - set(after))
    # Parenthesised deliberately: set difference binds tighter than union, so
    # `a | b - {""}` would strip the blank from b only and leave it in a.
    touched = sorted(
        (
            {after[k].get("state", "") for k in appeared}
            | {before[k].get("state", "") for k in disappeared}
        )
        - {""}
    )

    print(f"\n{'=' * 68}\n== What changed\n{'=' * 68}")
    print(f"  facilities before : {len(before)}")
    print(f"  facilities after  : {len(after)}")
    print(f"  appeared          : {len(appeared)}")
    print(f"  removed from OSM  : {len(disappeared)}")

    for key in appeared[:15]:
        row = after[key]
        name = row.get("name") or "(unnamed)"
        print(f"    + {name[:44]:<44} {row.get('state', '??')}")
    if len(appeared) > 15:
        print(f"    ... and {len(appeared) - 15} more")

    for key in disappeared[:15]:
        row = before[key]
        name = row.get("name") or "(unnamed)"
        # Never "demolished": ohsome cannot distinguish a building coming down
        # from a mapper changing its tags.
        print(f"    - {name[:44]:<44} {row.get('state', '??')} (removed from OSM)")
    if len(disappeared) > 15:
        print(f"    ... and {len(disappeared) - 15} more")

    if before:
        log = read_csv(POLL_LOG_PATH)
        log.append(
            {
                "polled_at": datetime.now(tz=UTC).date().isoformat(),
                "facilities_before": str(len(before)),
                "facilities_after": str(len(after)),
                "appeared": str(len(appeared)),
                "disappeared": str(len(disappeared)),
                "states_touched": " ".join(touched),
            }
        )
        write_csv(POLL_LOG_PATH, POLL_FIELDNAMES, log)
        print(f"\n  appended to {POLL_LOG_PATH.name}")

    if failed:
        print(f"\n  stages that did not complete: {', '.join(failed)}")

    print("\nNext: review `git diff data/observatory`, then commit and push to deploy.")
    return 1 if failed and "assign_regions.py" in failed else 0


if __name__ == "__main__":
    sys.exit(main())
