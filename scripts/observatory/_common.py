"""Shared plumbing for the observatory data scripts.

These scripts are deliberately independent of the Postgres/FastAPI stack. They
read public APIs, write CSV, and need no database, no migrations and no running
services - so a contributor can refresh the published data with a checkout and a
virtualenv alone.

Two properties matter more than convenience here:

**Byte-stability.** Re-running a fetch when nothing upstream has changed must
produce an identical file. That is what makes ``git diff`` a truthful change
log: a diff always means real movement, never a re-serialisation artefact. Every
writer therefore sorts its rows on a stable key and formats floats to a fixed
precision.

**Loud failure.** A throttled or truncated run must never write a file that
looks complete. Zero rows returned under a rate limit is not evidence of zero
data centres, and a partial CSV that silently replaces a full one would publish
a coverage collapse as though it were a finding.
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx

from helios_common.config import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "observatory"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
CACHE_DIR = REPO_ROOT / "data" / "observatory" / ".cache"

# Coordinates are stored to 6 decimal places (~0.1 m). Beyond that the digits are
# noise from projection round-trips, and they would churn the diff on every run.
COORD_PRECISION = 6
AREA_PRECISION = 1

# The tag combinations that constitute a data centre in OpenStreetMap. The wiki
# documents `telecom=data_center` as the primary tag, `building=data_center` for
# purpose-built structures, and `industrial=data_centre` (British spelling) for
# large campuses tagged as industrial landuse.
OSM_DATA_CENTRE_FILTERS: tuple[str, ...] = (
    'nwr["telecom"="data_center"]',
    'nwr["building"="data_center"]',
    'nwr["industrial"="data_centre"]',
)
OHSOME_FILTER = "telecom=data_center or building=data_center or industrial=data_centre"

# Overpass mirrors, in preference order. The main instance leads on two measured
# grounds: it answered a dense 12x7-degree extract in 11 s where the Kumi mirror
# took 42 s for an *empty* tile, and its database was current where Kumi's was
# two months behind. Freshness is the deciding factor - a stale mirror would
# silently report recent facilities as not yet existing, which is precisely the
# false negative this project must not produce.
OVERPASS_MIRRORS: tuple[str, ...] = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OHSOME_BASE = "https://api.ohsome.org/v1"


class FetchError(RuntimeError):
    """Raised when an upstream source cannot be read completely.

    Deliberately fatal. The alternative - writing whatever arrived - turns a
    transport failure into a published claim that facilities disappeared.
    """


class BoundingBox:
    """A geographic bounding box in WGS-84 degrees."""

    def __init__(self, west: float, south: float, east: float, north: float) -> None:
        """Initialise the box from its four edges.

        Args:
            west: Minimum longitude.
            south: Minimum latitude.
            east: Maximum longitude.
            north: Maximum latitude.
        """
        self.west = west
        self.south = south
        self.east = east
        self.north = north

    def as_overpass(self) -> str:
        """Render as an Overpass QL bbox filter (south,west,north,east)."""
        return f"({self.south},{self.west},{self.north},{self.east})"

    def as_ohsome(self) -> str:
        """Render as an ohsome ``bboxes`` value (west,south,east,north)."""
        return f"{self.west},{self.south},{self.east},{self.north}"

    def key(self) -> str:
        """Return a filesystem-safe identifier, used to name cache entries."""
        return f"{self.west:.2f}_{self.south:.2f}_{self.east:.2f}_{self.north:.2f}".replace(
            "-", "m"
        )

    def __repr__(self) -> str:
        """Return a compact debugging representation."""
        return f"BoundingBox({self.west}, {self.south}, {self.east}, {self.north})"


# The United States in four pieces. Splitting them keeps the empty Pacific out of
# the request envelope, which is what makes the per-tile queries small enough for
# Overpass to answer without timing out.
US_REGIONS: dict[str, BoundingBox] = {
    "conus": BoundingBox(-125.0, 24.0, -66.5, 49.5),
    # Trimmed to the road-connected south and interior. The Aleutian chain and
    # the far north are excluded deliberately: they add a dozen tiles of empty
    # ocean and hold no data centres. If that ever stops being true, widen it.
    "alaska": BoundingBox(-166.0, 54.0, -130.0, 66.0),
    "hawaii": BoundingBox(-161.0, 18.5, -154.0, 22.5),
    "puerto-rico": BoundingBox(-68.0, 17.8, -64.5, 18.6),
}


def tile(box: BoundingBox, degrees: float) -> list[BoundingBox]:
    """Split ``box`` into a grid of tiles at most ``degrees`` on a side.

    Tiling exists because Overpass returns 504 for a whole-country extract. Tiles
    overlap at their shared edges by construction, so callers must de-duplicate
    on the OSM identifier - a facility straddling a boundary is returned twice.

    Args:
        box: The area to split.
        degrees: Maximum tile width and height, in degrees.

    Returns:
        Tiles in a stable west-to-east, south-to-north order.
    """
    if degrees <= 0:
        raise ValueError("Tile size must be positive")
    cols = max(1, math.ceil((box.east - box.west) / degrees))
    rows = max(1, math.ceil((box.north - box.south) / degrees))
    width = (box.east - box.west) / cols
    height = (box.north - box.south) / rows
    tiles: list[BoundingBox] = []
    for row in range(rows):
        for col in range(cols):
            tiles.append(
                BoundingBox(
                    west=box.west + col * width,
                    south=box.south + row * height,
                    east=box.west + (col + 1) * width,
                    north=box.south + (row + 1) * height,
                )
            )
    return tiles


def us_tiles(degrees: float) -> list[tuple[str, BoundingBox]]:
    """Return every tile covering the United States, labelled by region."""
    out: list[tuple[str, BoundingBox]] = []
    for name, box in US_REGIONS.items():
        for index, piece in enumerate(tile(box, degrees)):
            out.append((f"{name}-{index:03d}", piece))
    return out


def user_agent() -> str:
    """Return the project User-Agent.

    Overpass and ohsome are volunteer-run. Identifying the client is the minimum
    courtesy owed to infrastructure nobody is paying for.
    """
    return str(get_settings().user_agent)


def post_form(
    urls: Sequence[str],
    data: dict[str, str],
    *,
    timeout: float = 300.0,
    attempts: int = 3,
    label: str = "request",
) -> dict[str, Any]:
    """POST a form to the first URL that answers, retrying with backoff.

    Tries each URL in turn; on exhaustion of all of them it waits and starts
    again, so a mirror that is briefly busy is not written off permanently.

    Args:
        urls: Candidate endpoints, in preference order.
        data: Form fields to send.
        timeout: Per-attempt timeout in seconds.
        attempts: Number of passes over the full mirror list.
        label: Human-readable name used in error messages.

    Returns:
        The decoded JSON body.

    Raises:
        FetchError: When every mirror failed on every pass.
    """
    headers = {"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"}
    problems: list[str] = []
    for attempt in range(1, attempts + 1):
        for url in urls:
            host = url.split("/")[2]
            started = time.monotonic()
            try:
                response = httpx.post(url, data=data, headers=headers, timeout=timeout)
            except httpx.HTTPError as exc:  # transport-level failure
                elapsed = time.monotonic() - started
                # Printed, not swallowed: a run that silently falls back to a
                # slower or staler mirror looks identical to a healthy one.
                print(f"    {host} {type(exc).__name__} after {elapsed:.0f}s")
                problems.append(f"{url}: {type(exc).__name__}")
                continue
            elapsed = time.monotonic() - started
            if response.status_code == 200:
                try:
                    return dict(response.json())
                except json.JSONDecodeError:
                    print(f"    {host} returned 200 with a non-JSON body after {elapsed:.0f}s")
                    problems.append(f"{url}: 200 but body was not JSON")
                    continue
            print(f"    {host} HTTP {response.status_code} after {elapsed:.0f}s")
            problems.append(f"{url}: HTTP {response.status_code}")
        if attempt < attempts:
            # Linear rather than exponential: these are shared public services
            # and the useful signal is "come back later", not "hammer sooner".
            delay = 15.0 * attempt
            print(f"    all mirrors failed for {label}; waiting {delay:.0f}s")
            time.sleep(delay)
    raise FetchError(f"Could not fetch {label}. Attempts: " + "; ".join(problems[-6:]))


def get_json(url: str, params: dict[str, str] | None = None, *, timeout: float = 300.0) -> Any:
    """GET a URL and decode JSON, raising :class:`FetchError` on any failure."""
    headers = {"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"}
    try:
        response = httpx.get(url, params=params, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise FetchError(f"{url}: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise FetchError(f"{url}: HTTP {response.status_code}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise FetchError(f"{url}: 200 but body was not JSON") from exc


def cache_path(namespace: str, key: str) -> Path:
    """Return the cache file for one tile of one fetch stage."""
    return CACHE_DIR / namespace / f"{key}.json"


def read_cache(namespace: str, key: str) -> dict[str, Any] | None:
    """Return a cached payload, or ``None`` when it has not been fetched yet."""
    path = cache_path(namespace, key)
    if not path.exists():
        return None
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def write_cache(namespace: str, key: str, payload: dict[str, Any]) -> None:
    """Persist a payload so an interrupted run can resume without refetching."""
    path = cache_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def fmt_coord(value: float) -> str:
    """Format a coordinate at fixed precision so the diff stays stable."""
    return f"{value:.{COORD_PRECISION}f}"


def fmt_area(value: float) -> str:
    """Format an area in square metres at fixed precision."""
    return f"{value:.{AREA_PRECISION}f}"


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> int:
    """Write ``rows`` to ``path`` deterministically.

    Rows are written in the order supplied - callers sort them - with Unix line
    endings and no trailing whitespace, so that an unchanged dataset produces an
    unchanged file.

    Args:
        path: Destination file.
        fieldnames: Column order.
        rows: Row dictionaries.

    Returns:
        The number of data rows written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV written by :func:`write_csv`, returning an empty list if absent."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_progress(items: Sequence[Any], label: str) -> Iterator[tuple[int, Any]]:
    """Yield ``(index, item)`` while printing single-line progress."""
    total = len(items)
    for index, item in enumerate(items, start=1):
        print(f"  [{index:>3}/{total}] {label} {item[0] if isinstance(item, tuple) else item}")
        yield index, item
