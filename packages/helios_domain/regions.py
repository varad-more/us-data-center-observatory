"""Registered study regions.

``Site.region_slug`` is a plain string column, because a region is data rather
than schema and adding one should not need a migration. This module is what
stops it behaving like a *free* string. A region names the state whose code
prefixes project codes, the counties whose records Helios reads, and the cities
a parcel sweep is restricted to.

That tuple of cities was previously copied into six places — the worker CLI and
five test modules — which is precisely how a region drifts apart from itself.
Here it is written once.

Coverage is stated, not implied
-------------------------------
A region Helios has *named* is not a region Helios has *read*. Only
:attr:`RegionCoverage.ACTIVE` regions have connectors behind them; the rest are
``DECLARED`` — in scope, on the map of intent, and empty. This mirrors
``ConnectorStatus`` in the source registry for the same reason: the honest
thing to publish is the gap, not silence about it. Nothing here should ever be
read as a claim that Helios is watching a place.

Bounding boxes are deliberately generous. They bound a candidate query, and
over-inclusion is corrected downstream by county and city filters, whereas
under-inclusion silently drops real sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "DEFAULT_REGION_SLUG",
    "EAST_VALLEY_AZ",
    "REGIONS",
    "Region",
    "RegionCoverage",
    "UnknownRegionError",
    "active_regions",
    "get_region",
    "region_slugs",
    "resolve_region",
]


class RegionCoverage(StrEnum):
    """How much of a region Helios actually reads."""

    ACTIVE = "active"
    """Connectors ingest here; sites in this region rest on real records."""

    DECLARED = "declared"
    """Named as in scope. No connector reads it yet, so it holds no sites."""


class UnknownRegionError(KeyError):
    """Raised when a region slug is not in the registry."""


@dataclass(frozen=True, slots=True)
class Region:
    """A geography Helios tracks, or intends to.

    Attributes:
        slug: Stable identifier stored in ``sites.region_slug``.
        name: Human-readable name for display.
        state_code: Two-letter USPS code; prefixes every project code minted here.
        coverage: Whether connectors actually read this region.
        counties: Counties whose assessor and permit records cover the region.
        cities: Municipalities a parcel sweep is restricted to.
        bbox: ``(min_lon, min_lat, max_lon, max_lat)``, generous by design.
        note: Why this region is on the list.
    """

    slug: str
    name: str
    state_code: str
    coverage: RegionCoverage
    counties: tuple[str, ...]
    cities: tuple[str, ...]
    bbox: tuple[float, float, float, float]
    note: str

    @property
    def primary_county(self) -> str:
        """The county a site defaults to when a record does not name one."""
        return self.counties[0]

    @property
    def cities_upper(self) -> tuple[str, ...]:
        """City names upper-cased, matching how assessor feeds store them."""
        return tuple(city.upper() for city in self.cities)

    @property
    def is_active(self) -> bool:
        """Whether any connector reads this region today."""
        return self.coverage is RegionCoverage.ACTIVE

    def project_code_prefix(self, jurisdiction_fragment: str) -> str:
        """Build the project-code prefix for a jurisdiction in this region.

        Args:
            jurisdiction_fragment: Already-slugified city fragment, e.g. ``MESA``.

        Returns:
            A prefix such as ``AZ-MESA``.
        """
        return f"{self.state_code}-{jurisdiction_fragment}"


EAST_VALLEY_AZ = Region(
    slug="east-valley-az",
    name="East Valley, Arizona",
    state_code="AZ",
    coverage=RegionCoverage.ACTIVE,
    counties=("Maricopa", "Pinal"),
    cities=("Mesa", "Chandler", "Tempe", "Gilbert", "Queen Creek", "Apache Junction"),
    bbox=(-111.98, 33.16, -111.35, 33.52),
    note=(
        "The pilot region. Chosen because Maricopa County publishes parcel "
        "geometry, ownership and land-use classification openly, which makes it "
        "possible to check Helios against records anyone else can read."
    ),
)
"""The one region Helios currently ingests."""


REGIONS: tuple[Region, ...] = (
    EAST_VALLEY_AZ,
    Region(
        slug="phoenix-west-valley-az",
        name="West Valley, Arizona",
        state_code="AZ",
        coverage=RegionCoverage.DECLARED,
        counties=("Maricopa",),
        cities=("Goodyear", "Buckeye", "Avondale", "El Mirage", "Surprise", "Glendale"),
        bbox=(-112.75, 33.20, -112.05, 33.80),
        note=(
            "Same county records as the pilot, so the marginal cost of covering "
            "it is a city list rather than a connector."
        ),
    ),
    Region(
        slug="northern-virginia",
        name="Northern Virginia",
        state_code="VA",
        coverage=RegionCoverage.DECLARED,
        counties=("Loudoun", "Prince William", "Fairfax"),
        cities=("Ashburn", "Sterling", "Leesburg", "Manassas", "Chantilly", "Herndon"),
        bbox=(-77.85, 38.55, -77.00, 39.35),
        note="The largest concentration of data-centre capacity in the world.",
    ),
    Region(
        slug="central-ohio",
        name="Central Ohio",
        state_code="OH",
        coverage=RegionCoverage.DECLARED,
        counties=("Franklin", "Licking", "Delaware"),
        cities=("Columbus", "New Albany", "Hilliard", "Dublin", "Johnstown"),
        bbox=(-83.30, 39.75, -82.30, 40.40),
        note="Fast-growing hyperscale cluster with active county GIS portals.",
    ),
    Region(
        slug="dfw-texas",
        name="Dallas-Fort Worth, Texas",
        state_code="TX",
        coverage=RegionCoverage.DECLARED,
        counties=("Dallas", "Tarrant", "Denton", "Ellis"),
        cities=("Dallas", "Fort Worth", "Plano", "Irving", "Garland", "Midlothian"),
        bbox=(-97.60, 32.35, -96.35, 33.30),
        note="Inside ERCOT, whose generation reporting is machine-readable.",
    ),
    Region(
        slug="atlanta-georgia",
        name="Atlanta metro, Georgia",
        state_code="GA",
        coverage=RegionCoverage.DECLARED,
        counties=("Fulton", "Douglas", "Coweta", "DeKalb"),
        cities=("Atlanta", "Douglasville", "Lithia Springs", "Newnan", "Palmetto"),
        bbox=(-85.00, 33.20, -83.90, 34.15),
        note="Rapid buildout against a constrained transmission network.",
    ),
    Region(
        slug="salt-lake-utah",
        name="Salt Lake Valley, Utah",
        state_code="UT",
        coverage=RegionCoverage.DECLARED,
        counties=("Salt Lake", "Utah", "Tooele"),
        cities=("Salt Lake City", "West Jordan", "Bluffdale", "Eagle Mountain", "Lehi"),
        bbox=(-112.30, 40.30, -111.60, 41.00),
        note="Arid, like the pilot region, which makes water estimates comparable.",
    ),
    Region(
        slug="chicago-illinois",
        name="Chicago metro, Illinois",
        state_code="IL",
        coverage=RegionCoverage.DECLARED,
        counties=("Cook", "DuPage", "Kane", "Will"),
        cities=("Chicago", "Elk Grove Village", "Aurora", "Northlake", "Franklin Park"),
        bbox=(-88.75, 41.35, -87.50, 42.20),
        note="Dense interconnection hub; strong county open-data publishing.",
    ),
    Region(
        slug="santa-clara-california",
        name="Santa Clara County, California",
        state_code="CA",
        coverage=RegionCoverage.DECLARED,
        counties=("Santa Clara",),
        cities=("Santa Clara", "San Jose", "Sunnyvale", "Milpitas"),
        bbox=(-122.20, 36.90, -121.20, 37.50),
        note="A municipal utility publishes load data no investor-owned utility does.",
    ),
)
"""Every region Helios names. Exactly one of them is currently read."""


DEFAULT_REGION_SLUG = EAST_VALLEY_AZ.slug
"""The region a command assumes when none is given."""


_BY_SLUG: dict[str, Region] = {region.slug: region for region in REGIONS}


def get_region(slug: str) -> Region:
    """Look up a region by slug.

    Args:
        slug: Region identifier, e.g. ``east-valley-az``.

    Returns:
        The registered region.

    Raises:
        UnknownRegionError: If no region carries that slug.
    """
    try:
        return _BY_SLUG[slug]
    except KeyError:
        known = ", ".join(sorted(_BY_SLUG))
        raise UnknownRegionError(f"Unknown region {slug!r}. Registered regions: {known}") from None


def resolve_region(region: Region | str) -> Region:
    """Accept either a region or its slug.

    Lets callers pass whichever they have without every call site repeating the
    lookup.

    Args:
        region: A region, or a registered slug.

    Returns:
        The region.

    Raises:
        UnknownRegionError: If a slug is given and is not registered.
    """
    return region if isinstance(region, Region) else get_region(region)


def region_slugs() -> tuple[str, ...]:
    """Every registered slug, in registry order."""
    return tuple(region.slug for region in REGIONS)


def active_regions() -> tuple[Region, ...]:
    """Only the regions a connector actually reads."""
    return tuple(region for region in REGIONS if region.is_active)


def _validate_registry() -> None:
    """Fail at import if the registry contradicts itself.

    A malformed region would otherwise surface as a project code with a blank
    state prefix, or a bounding box that quietly matches nothing.
    """
    seen: set[str] = set()
    for region in REGIONS:
        if region.slug in seen:
            raise ValueError(f"Duplicate region slug: {region.slug}")
        seen.add(region.slug)

        if len(region.state_code) != 2 or not region.state_code.isupper():
            raise ValueError(f"{region.slug}: state_code must be two upper-case letters")
        if not region.counties:
            raise ValueError(f"{region.slug}: at least one county is required")
        if region.is_active and not region.cities:
            raise ValueError(f"{region.slug}: an active region must name its cities")

        min_lon, min_lat, max_lon, max_lat = region.bbox
        if min_lon >= max_lon or min_lat >= max_lat:
            raise ValueError(f"{region.slug}: bbox corners are inverted")
        if not (min_lon >= -180 and max_lon <= 180 and min_lat >= -90 and max_lat <= 90):
            raise ValueError(f"{region.slug}: bbox is outside valid coordinates")


_validate_registry()
