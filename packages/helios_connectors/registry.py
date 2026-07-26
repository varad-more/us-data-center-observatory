"""The Helios source registry.

Every source Helios reads is declared here *before* any code fetches from it.
The registry is the project's legal and operational memory: it records who
publishes the data, under what licence, at what rate limit, how far back the
history goes, and - when a source cannot be accessed responsibly - exactly what
blocks it.

Entries whose ``connector_status`` is ``PLANNED`` or ``FIXTURE_ONLY`` are as
important as working ones. They make the coverage gaps in Helios visible instead
of leaving users to assume the absence of evidence means the absence of activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from helios_common.vocabulary import AccessMethod, ConnectorStatus, SourceCategory

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class SourceRegistryEntry:
    """A declared public source with its access and licensing posture."""

    slug: str
    name: str
    agency: str
    jurisdiction: str
    category: SourceCategory
    base_url: str
    access_method: AccessMethod
    connector_status: ConnectorStatus

    update_frequency: str | None = None
    requires_authentication: bool = False
    authentication_notes: str | None = None
    rate_limit_per_second: float | None = None
    rate_limit_notes: str | None = None

    license_name: str | None = None
    license_url: str | None = None
    licensing_notes: str | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    robots_policy_status: str | None = None
    terms_of_service_url: str | None = None

    geographic_coverage: str | None = None
    historical_coverage: str | None = None
    contains_personal_data: bool = False
    reliability_score: float | None = None
    known_schema_issues: str | None = None
    access_limitation: str | None = None
    notes: str | None = None
    connector_slug: str | None = None
    connector_entry_point: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


_EAST_VALLEY = "Mesa, Chandler, Tempe, Gilbert, Queen Creek, Apache Junction, Maricopa County"


SOURCE_REGISTRY: tuple[SourceRegistryEntry, ...] = (
    # ------------------------------------------------ land and property ----
    SourceRegistryEntry(
        slug="maricopa-assessor-parcels",
        name="Maricopa County Assessor Parcel Layer",
        agency="Maricopa County Assessor / Maricopa County GIS",
        jurisdiction="Maricopa County, Arizona",
        category=SourceCategory.LAND_AND_PROPERTY,
        base_url="https://gis.maricopa.gov/arcgis/rest/services/RED/Assessor/MapServer",
        access_method=AccessMethod.ARCGIS_REST,
        connector_status=ConnectorStatus.IMPLEMENTED,
        update_frequency="daily",
        rate_limit_per_second=2.0,
        rate_limit_notes=(
            "No published limit. Helios self-imposes 2 rps and pages at the service's "
            "2000-record maximum."
        ),
        license_name="Maricopa County open GIS data",
        license_url="https://gis.maricopa.gov/",
        licensing_notes=(
            "Published for public use. County disclaims warranty of accuracy; parcel "
            "geometry is for reference and not a survey."
        ),
        attribution_required=True,
        attribution_text="Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS.",
        robots_policy_status="not_applicable",
        geographic_coverage="Maricopa County, Arizona",
        historical_coverage=(
            "Current assessment roll only. Exposes the most recent recorded deed per parcel, "
            "not the full transfer chain, which truncates observable ownership history."
        ),
        contains_personal_data=True,
        reliability_score=0.95,
        known_schema_issues=(
            "Date fields are epoch milliseconds. OwnerName is a single unstructured string "
            "mixing companies, trusts, and private individuals. Wide LIKE scans are slow "
            "(~24s observed), so queries should be bounded by geometry or city first."
        ),
        connector_slug="maricopa-assessor-parcels",
        connector_entry_point="helios_connectors.maricopa_assessor:MaricopaAssessorConnector",
        tags=("parcels", "ownership", "ground-truth"),
    ),
    SourceRegistryEntry(
        slug="maricopa-recorder-documents",
        name="Maricopa County Recorder Document Search",
        agency="Maricopa County Recorder",
        jurisdiction="Maricopa County, Arizona",
        category=SourceCategory.LAND_AND_PROPERTY,
        base_url="https://recorder.maricopa.gov/recording/document-details.html",
        access_method=AccessMethod.HTML_PAGE,
        connector_status=ConnectorStatus.PLANNED,
        update_frequency="daily",
        geographic_coverage="Maricopa County, Arizona",
        historical_coverage="Recorded instruments; deep historical coverage.",
        contains_personal_data=True,
        access_limitation=(
            "Individual recorded documents are reachable by recording number, and the "
            "assessor layer already supplies those numbers and deep links. Systematic "
            "enumeration is not attempted: it would constitute bulk retrieval of records "
            "containing personal information without a demonstrated need."
        ),
        notes=(
            "Helios links out to recorder documents for human verification rather than "
            "ingesting them."
        ),
        tags=("deeds", "outbound-link-only"),
    ),
    # -------------------------------------------- infrastructure reference --
    SourceRegistryEntry(
        slug="osm-power-infrastructure",
        name="OpenStreetMap Power Infrastructure (Overpass API)",
        agency="OpenStreetMap contributors",
        jurisdiction="Global (queried for the East Valley study area)",
        category=SourceCategory.INFRASTRUCTURE_REFERENCE,
        base_url="https://overpass-api.de/api/interpreter",
        access_method=AccessMethod.OVERPASS,
        connector_status=ConnectorStatus.IMPLEMENTED,
        update_frequency="continuous",
        rate_limit_per_second=0.5,
        rate_limit_notes=(
            "Overpass is a donated public endpoint with slot-based fair use. Helios keeps "
            "to 0.5 rps and issues one bounded bbox query per run."
        ),
        license_name="Open Database License (ODbL) 1.0",
        license_url="https://opendatacommons.org/licenses/odbl/1-0/",
        licensing_notes=(
            "ODbL requires attribution and share-alike on derived databases. Any Helios "
            "export containing OSM-derived geometry must carry the attribution below."
        ),
        attribution_required=True,
        attribution_text="Power infrastructure data (c) OpenStreetMap contributors, ODbL.",
        robots_policy_status="allowed",
        geographic_coverage="East Valley bounding box",
        historical_coverage=(
            "Current snapshot only via Overpass. Attic queries could provide history but are "
            "expensive and not used."
        ),
        reliability_score=0.7,
        known_schema_issues=(
            "Voltage is a semicolon-delimited string in volts. Completeness is "
            "contributor-dependent: absence of a substation is not evidence it does not exist."
        ),
        connector_slug="osm-power-infrastructure",
        connector_entry_point="helios_connectors.osm_power:OsmPowerConnector",
        tags=("substations", "transmission", "odbl"),
    ),
    # ---------------------------------------------------------- environmental --
    SourceRegistryEntry(
        slug="epa-echo-air-facilities",
        name="EPA ECHO Air Facility Records",
        agency="United States Environmental Protection Agency",
        jurisdiction="United States",
        category=SourceCategory.ENVIRONMENTAL,
        base_url="https://echodata.epa.gov/echo/air_rest_services.get_facilities",
        access_method=AccessMethod.REST_JSON,
        connector_status=ConnectorStatus.PLANNED,
        update_frequency="weekly",
        rate_limit_per_second=1.0,
        rate_limit_notes="No published limit; Helios self-imposes 1 rps.",
        license_name="US Government public domain",
        license_url="https://www.epa.gov/privacy/privacy-and-security-notice",
        licensing_notes="Federal public-domain data, freely redistributable.",
        robots_policy_status="allowed",
        geographic_coverage="Nationwide; queried per city within the study area",
        historical_coverage="Active and historical Clean Air Act permitted facilities.",
        reliability_score=0.85,
        known_schema_issues=(
            "Two-step API: a query call returns a QueryID that must be passed to the "
            "results call. Facility coordinates are sometimes geocoded rather than surveyed, "
            "so spatial matches need a distance tolerance."
        ),
        notes=(
            "Endpoint reachability was verified (17 permitted facilities returned for Mesa), "
            "but no connector has been written yet, so this source contributes nothing to "
            "the current evidence base. Backup-generator air permits are the most "
            "diagnostic non-spatial data-centre signal available, making this the highest-"
            "value connector to build next."
        ),
        tags=("air-permits", "generators", "federal", "next-sprint"),
    ),
    SourceRegistryEntry(
        slug="maricopa-aqd-dust-control",
        name="Maricopa County Air Quality Dust Control Sites",
        agency="Maricopa County Air Quality Department",
        jurisdiction="Maricopa County, Arizona",
        category=SourceCategory.ENVIRONMENTAL,
        base_url="https://gis.maricopa.gov/arcgis/rest/services/AQD/DustControl/MapServer",
        access_method=AccessMethod.ARCGIS_REST,
        connector_status=ConnectorStatus.PLANNED,
        update_frequency="daily",
        geographic_coverage="Maricopa County, Arizona",
        historical_coverage="Active dust-control registrations.",
        reliability_score=0.6,
        known_schema_issues=(
            "The Dust Control Site layer exposes only ImpactID and geometry; the permit "
            "attributes that would make it useful as a construction signal are not published "
            "through this service."
        ),
        notes=(
            "Deferred to a later sprint. Earth-disturbance registrations would be a strong "
            "Stage 4 signal if the attribute set can be joined from another AQD service."
        ),
        tags=("grading", "construction-signal"),
    ),
    # --------------------------------------------------- municipal planning --
    SourceRegistryEntry(
        slug="mesa-building-permits",
        name="City of Mesa Building Permits",
        agency="City of Mesa",
        jurisdiction="Mesa, Arizona",
        category=SourceCategory.MUNICIPAL_PLANNING,
        base_url="https://data.mesaaz.gov/resource/a2ui-hcuj.json",
        access_method=AccessMethod.SOCRATA,
        connector_status=ConnectorStatus.PLANNED,
        update_frequency="daily",
        rate_limit_per_second=2.0,
        rate_limit_notes="Socrata throttles unauthenticated clients; an app token raises limits.",
        license_name="City of Mesa open data",
        license_url="https://data.mesaaz.gov/",
        robots_policy_status="allowed",
        geographic_coverage="Mesa, Arizona",
        historical_coverage="Permits from approximately 2015 onward.",
        reliability_score=0.75,
        known_schema_issues=(
            "The public view exposes only permit number, type, address, status, and three "
            "dates. There is no valuation, work description, or applicant, and no coordinates, "
            "so permits must be matched to parcels by address string alone."
        ),
        notes=(
            "Deferred to the next sprint. Address-only matching needs the geospatial "
            "correlation module to be trustworthy."
        ),
        tags=("permits", "municipal"),
    ),
    SourceRegistryEntry(
        slug="mesa-planning-cases",
        name="City of Mesa Planning and Zoning Cases",
        agency="City of Mesa Development Services",
        jurisdiction="Mesa, Arizona",
        category=SourceCategory.MUNICIPAL_PLANNING,
        base_url="https://www.mesaaz.gov/business-development/planning-zoning",
        access_method=AccessMethod.HTML_PAGE,
        connector_status=ConnectorStatus.PLANNED,
        geographic_coverage="Mesa, Arizona",
        access_limitation=(
            "Planning cases are published as council and commission agenda attachments rather "
            "than a queryable dataset. Extraction requires PDF agenda parsing, which is "
            "scheduled for the document-intelligence sprint."
        ),
        tags=("zoning", "agendas", "pdf"),
    ),
    # ------------------------------------------------ utility and regulatory --
    SourceRegistryEntry(
        slug="azcc-edocket",
        name="Arizona Corporation Commission eDocket",
        agency="Arizona Corporation Commission",
        jurisdiction="Arizona",
        category=SourceCategory.UTILITY_AND_REGULATORY,
        base_url="https://edocket.azcc.gov/",
        access_method=AccessMethod.HTML_PAGE,
        connector_status=ConnectorStatus.FIXTURE_ONLY,
        update_frequency="daily",
        geographic_coverage="Arizona",
        historical_coverage="Utility dockets with deep history.",
        reliability_score=0.8,
        access_limitation=(
            "eDocket search is a stateful ASP.NET interface requiring viewstate round-trips "
            "and offering no documented API or bulk export. Helios implements and tests the "
            "parser against fixtures built from the documented docket schema, and does not "
            "automate the search interface. Live coverage requires either an agency-provided "
            "export or manual docket retrieval."
        ),
        notes=(
            "Transmission and substation filings here are the single highest-weight signal in "
            "the scoring model, so this gap materially limits Stage 3 recall. It is recorded "
            "prominently in the limitations documentation."
        ),
        connector_slug="azcc-edocket",
        connector_entry_point="helios_connectors.azcc_edocket:AzccEdocketConnector",
        tags=("transmission", "substation", "high-value", "blocked"),
    ),
    SourceRegistryEntry(
        slug="srp-infrastructure-projects",
        name="Salt River Project Infrastructure Projects",
        agency="Salt River Project",
        jurisdiction="SRP service territory, Arizona",
        category=SourceCategory.UTILITY_AND_REGULATORY,
        base_url="https://www.srpnet.com/grid-water-management/improvement-projects",
        access_method=AccessMethod.HTML_PAGE,
        connector_status=ConnectorStatus.PLANNED,
        geographic_coverage="SRP service territory including much of the East Valley",
        access_limitation=(
            "Project pages are marketing content without a stable structure or machine-readable "
            "index. Parsing is feasible but brittle and deferred."
        ),
        tags=("utility", "substation"),
    ),
    # ------------------------------------------------------------ corporate --
    SourceRegistryEntry(
        slug="az-corporation-commission-entity-search",
        name="Arizona Corporation Commission Entity Search",
        agency="Arizona Corporation Commission",
        jurisdiction="Arizona",
        category=SourceCategory.CORPORATE,
        base_url="https://ecorp.azcc.gov/",
        access_method=AccessMethod.HTML_PAGE,
        connector_status=ConnectorStatus.PLANNED,
        contains_personal_data=True,
        access_limitation=(
            "eCorp is an interactive search application. Registered-agent and officer records "
            "contain personal information, so Helios will only ingest entity-level fields "
            "(name, formation date, status) if a compliant access path is established."
        ),
        notes=(
            "Would substantially improve shell-company resolution. Held back deliberately "
            "pending a privacy review."
        ),
        tags=("shell-companies", "entity-resolution", "privacy-sensitive"),
    ),
    SourceRegistryEntry(
        slug="sec-edgar",
        name="SEC EDGAR Full-Text Search",
        agency="US Securities and Exchange Commission",
        jurisdiction="United States",
        category=SourceCategory.CORPORATE,
        base_url="https://efts.sec.gov/LATEST/search-index",
        access_method=AccessMethod.REST_JSON,
        connector_status=ConnectorStatus.PLANNED,
        rate_limit_per_second=10.0,
        rate_limit_notes="SEC requires a descriptive User-Agent and caps at 10 requests/second.",
        license_name="US Government public domain",
        robots_policy_status="allowed",
        geographic_coverage="United States",
        historical_coverage="Filings from 2001 onward in full-text search.",
        notes="Useful for confirming operator identity from primary filings rather than inference.",
        tags=("filings", "attribution"),
    ),
    # ---------------------------------------------------------- remote sensing --
    SourceRegistryEntry(
        slug="copernicus-sentinel2",
        name="Copernicus Sentinel-2 Surface Reflectance",
        agency="European Space Agency / Copernicus",
        jurisdiction="Global",
        category=SourceCategory.REMOTE_SENSING,
        base_url="https://catalogue.dataspace.copernicus.eu/",
        access_method=AccessMethod.REST_JSON,
        connector_status=ConnectorStatus.PLANNED,
        requires_authentication=True,
        authentication_notes="Requires a free registered Copernicus Data Space account.",
        license_name="Copernicus open licence",
        geographic_coverage="Global",
        historical_coverage="2015 onward.",
        access_limitation=(
            "No Copernicus credentials are configured in this environment, so no satellite "
            "imagery has been acquired or analysed. Remote sensing is out of scope for this "
            "sprint and no satellite observations exist in the database."
        ),
        tags=("satellite", "future-phase"),
    ),
    # -------------------------------------------------------------- water ----
    SourceRegistryEntry(
        slug="adwr-water-records",
        name="Arizona Department of Water Resources Data",
        agency="Arizona Department of Water Resources",
        jurisdiction="Arizona",
        category=SourceCategory.WATER,
        base_url="https://new.azwater.gov/data",
        access_method=AccessMethod.BULK_DOWNLOAD,
        connector_status=ConnectorStatus.PLANNED,
        geographic_coverage="Arizona, including the Phoenix Active Management Area",
        historical_coverage="Long historical series for groundwater and withdrawals.",
        notes="Needed before any water-use scenario is published. Deferred.",
        tags=("water", "future-phase"),
    ),
)


def iter_registry() -> Iterator[SourceRegistryEntry]:
    """Iterate over every declared source."""
    return iter(SOURCE_REGISTRY)


def get_entry(slug: str) -> SourceRegistryEntry:
    """Look up a registry entry by slug.

    Args:
        slug: The source slug.

    Returns:
        The matching entry.

    Raises:
        KeyError: If no source with that slug is declared.
    """
    for entry in SOURCE_REGISTRY:
        if entry.slug == slug:
            return entry
    raise KeyError(f"No source registry entry with slug {slug!r}")


def implemented_entries() -> list[SourceRegistryEntry]:
    """Return entries whose connectors can actually run (live or fixture-backed)."""
    runnable = {ConnectorStatus.IMPLEMENTED, ConnectorStatus.FIXTURE_ONLY}
    return [e for e in SOURCE_REGISTRY if e.connector_status in runnable]


def registry_coverage_summary() -> dict[str, int]:
    """Count sources by connector status, for the observability dashboard."""
    summary: dict[str, int] = {}
    for entry in SOURCE_REGISTRY:
        key = str(entry.connector_status)
        summary[key] = summary.get(key, 0) + 1
    return summary


__all__ = [
    "SOURCE_REGISTRY",
    "SourceRegistryEntry",
    "get_entry",
    "implemented_entries",
    "iter_registry",
    "registry_coverage_summary",
]
