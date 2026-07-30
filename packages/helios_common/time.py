"""Time handling with an explicit separation of Helios's three clocks.

Helios distinguishes:

* **valid time** - when a fact was true in the world (``effective_start``)
* **transaction time** - when Helios learned it (``retrieved_at``)
* **document time** - when the source published it (``published_date``)

Backtesting filters on valid and document time; audit uses transaction time.
Conflating them silently leaks future information into historical replays, so
everything here returns timezone-aware UTC values and refuses naive datetimes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from dateutil import parser as dateutil_parser

_EPOCH_MS_THRESHOLD = 100_000_000_000
"""Values above this are treated as milliseconds; ArcGIS emits epoch millis."""


def utcnow() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(tz=UTC)


def from_epoch_millis(value: int | float | None) -> datetime | None:
    """Convert an ArcGIS-style epoch timestamp to UTC.

    ArcGIS date fields arrive as epoch milliseconds, but some feeds mix in
    seconds. The magnitude disambiguates.

    Args:
        value: Epoch timestamp in seconds or milliseconds, or ``None``.

    Returns:
        UTC datetime, or ``None`` if the input was ``None``.
    """
    if value is None:
        return None
    seconds = value / 1000.0 if abs(value) >= _EPOCH_MS_THRESHOLD else float(value)
    return datetime.fromtimestamp(seconds, tz=UTC)


def parse_flexible_date(raw: str | None, *, dayfirst: bool = False) -> date | None:
    """Parse a date from unpredictable public-record formatting.

    Public agencies publish dates as ``03/14/2025``, ``March 14, 2025``,
    ``2025-03-14T00:00:00.000`` and worse. Returns ``None`` rather than raising
    so that a single malformed field does not abort a whole document.

    Args:
        raw: Candidate date string.
        dayfirst: Interpret ambiguous numeric dates as day-first.

    Returns:
        The parsed calendar date, or ``None`` when unparseable.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = dateutil_parser.parse(text, dayfirst=dayfirst, fuzzy=False)
    except (ValueError, OverflowError, TypeError):
        return None
    return parsed.date()
