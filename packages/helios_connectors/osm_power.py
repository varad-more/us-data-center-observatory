"""Connector for electrical infrastructure from OpenStreetMap via the Overpass API.

Substations and transmission lines are the highest-weight signals in the Helios
scoring model, because a hyperscale campus cannot exist without grid capacity and
grid capacity is expensive, slow, and visible long before a building is.

Why OpenStreetMap
-----------------
Utility-published GIS for Arizona is either absent or embedded in unstructured
project pages. OSM is the only openly licensed, machine-readable, immediately
queryable source of substation geometry, voltage, and operator for this region.
Its weakness is that coverage is contributor-dependent, so the connector treats
it as *corroborating* rather than authoritative and records a modest reliability
score. **The absence of a substation in OSM is not evidence that none exists**,
and nothing in Helios may draw a negative inference from it.

Licensing
---------
OSM data is ODbL 1.0, which requires attribution and imposes share-alike
obligations on derived databases. The connector metadata carries the attribution
string, and every export that includes OSM-derived geometry must reproduce it.

Rate limiting
-------------
Overpass is donated infrastructure with slot-based fair use. The connector issues
exactly one bounded bbox query per run and self-limits to 0.5 requests/second.
"""

from __future__ import annotations

import json
from typing import Any

from helios_common.config import Settings
from helios_common.logging import get_logger
from helios_common.time import utcnow
from helios_common.vocabulary import (
    AccessMethod,
    AssertionClass,
    ConnectorStatus,
    ExtractionMethod,
    SourceCategory,
)
from helios_connectors.base import BaseConnector
from helios_connectors.http import PoliteHttpClient
from helios_connectors.types import (
    ConnectorMetadata,
    DateRange,
    DiscoveryResult,
    ExtractedField,
    FetchResult,
    HealthCheckResult,
    NormalizationResult,
    NormalizedRecord,
    ParsedDocument,
    ParseResult,
    RawDocument,
    SourceItem,
)
from helios_document_intelligence.units import parse_voltage_list

logger = get_logger(__name__)

CONNECTOR_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
STATUS_URL = "https://overpass-api.de/api/status"

TRANSMISSION_VOLTAGE_KV = 115.0
"""At and above this, a circuit is transmission rather than distribution and can
plausibly serve a large load."""

HYPERSCALE_RELEVANT_KV = 230.0
"""Voltage class typically associated with dedicated hyperscale service in this region."""


class OsmPowerConnector(BaseConnector):
    """Reads substations and transmission lines from the Overpass API."""

    def __init__(
        self,
        *,
        http_client: PoliteHttpClient | None = None,
        settings: Settings | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        min_voltage_kv: float = TRANSMISSION_VOLTAGE_KV,
    ) -> None:
        """Initialise the connector.

        Args:
            http_client: Shared HTTP client.
            settings: Configuration override.
            bbox: ``(min_lon, min_lat, max_lon, max_lat)``; defaults to the study region.
            min_voltage_kv: Lines below this are ignored as distribution.
        """
        super().__init__(http_client=http_client, settings=settings)
        self._bbox = bbox
        self.min_voltage_kv = min_voltage_kv

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """The query bounding box, defaulting to the configured study region."""
        if self._bbox is not None:
            return self._bbox
        return (self._settings or self.http.settings).study_region_bbox

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="osm-power-infrastructure",
            source_slug="osm-power-infrastructure",
            name="OpenStreetMap Power Infrastructure (Overpass API)",
            agency="OpenStreetMap contributors",
            jurisdiction="Global (queried for the East Valley study area)",
            category=SourceCategory.INFRASTRUCTURE_REFERENCE,
            access_method=AccessMethod.OVERPASS,
            base_url=OVERPASS_URL,
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.IMPLEMENTED,
            update_frequency="continuous",
            rate_limit_per_second=0.5,
            license_name="Open Database License (ODbL) 1.0",
            license_url="https://opendatacommons.org/licenses/odbl/1-0/",
            attribution_required=True,
            attribution_text="Power infrastructure data (c) OpenStreetMap contributors, ODbL.",
            robots_policy_status="allowed",
            geographic_coverage="East Valley bounding box",
            historical_coverage="Current snapshot only; attic queries are not used.",
            reliability_score=0.7,
            known_schema_issues=(
                "Voltage is a semicolon-delimited string in volts. Coverage is "
                "contributor-dependent, so absence must never be read as evidence of absence."
            ),
        )

    def health_check(self) -> HealthCheckResult:
        """Query the Overpass status endpoint, which reports available slots."""
        started = utcnow()
        try:
            response = self.http.get(STATUS_URL)
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, checked_at=started, message=f"{type(exc).__name__}: {exc}"
            )
        body = response.content.decode("utf-8", errors="replace")
        return HealthCheckResult(
            healthy=response.status_code == 200,
            checked_at=started,
            latency_ms=response.elapsed_ms,
            http_status=response.status_code,
            message=body.splitlines()[0] if body else None,
        )

    def build_query(self) -> str:
        """Build the Overpass QL query for the configured bounding box.

        Returns:
            An Overpass QL program requesting substations and power lines.
        """
        min_lon, min_lat, max_lon, max_lat = self.bbox
        area = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        return (
            "[out:json][timeout:90];"
            "("
            f'node["power"="substation"]({area});'
            f'way["power"="substation"]({area});'
            f'relation["power"="substation"]({area});'
            f'way["power"="line"]({area});'
            ");"
            "out center tags;"
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Return the single bounded query this connector issues per run.

        Overpass has no incremental change feed available within fair use, so
        each run is a full snapshot of the study area. Document versioning is what
        makes that acceptable: an unchanged snapshot produces no new version.

        Args:
            date_range: Unused; Overpass serves only current state.

        Returns:
            A discovery result containing exactly one item.
        """
        min_lon, min_lat, max_lon, max_lat = self.bbox
        item = SourceItem(
            source_native_id=f"overpass:power:{min_lon},{min_lat},{max_lon},{max_lat}",
            url=OVERPASS_URL,
            title="East Valley power infrastructure snapshot",
            document_type="overpass_json",
            hints={"query": self.build_query()},
        )
        return DiscoveryResult(
            items=[item],
            detail={"note": "Overpass serves current state only; date range is not applied."},
        )

    def fetch(self, item: SourceItem) -> FetchResult:
        """Execute the Overpass query."""
        query = item.hints.get("query") or self.build_query()
        try:
            response = self.http.post(
                item.url, data={"data": query}, headers={"Accept": "application/json"}
            )
        except Exception as exc:
            return FetchResult(document=None, error=f"{type(exc).__name__}: {exc}")

        return FetchResult(
            document=RawDocument(
                item=item,
                payload=response.content,
                mime_type="application/json",
                retrieved_at=utcnow(),
                http_status=response.status_code,
                headers=response.headers,
                etag=response.etag,
                last_modified=response.last_modified,
            )
        )

    def parse(self, document: RawDocument) -> ParseResult:
        """Decode an Overpass JSON response into element records."""
        try:
            payload = json.loads(document.payload)
        except json.JSONDecodeError as exc:
            return ParseResult(document=None, error=f"Invalid JSON: {exc}")

        if "elements" not in payload:
            remark = payload.get("remark", "no 'elements' key in response")
            return ParseResult(document=None, error=f"Unexpected Overpass payload: {remark}")

        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        for index, element in enumerate(payload["elements"]):
            tags = element.get("tags") or {}
            if not tags.get("power"):
                continue
            records.append(
                {
                    "osm_type": element.get("type"),
                    "osm_id": element.get("id"),
                    "power": tags.get("power"),
                    "tags": tags,
                    "lat": element.get("lat") or (element.get("center") or {}).get("lat"),
                    "lon": element.get("lon") or (element.get("center") or {}).get("lon"),
                    "_locator": f"$.elements[{index}]",
                }
            )

        if remark := payload.get("remark"):
            # Overpass reports timeouts and memory limits in `remark` while still
            # returning a 200, so a truncated result would otherwise look complete.
            warnings.append(f"Overpass remark: {remark}")

        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="overpass_json",
                records=records,
                field_signature=self.field_signature(
                    [{"power": r["power"], **r["tags"]} for r in records[:200]]
                ),
                warnings=warnings,
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Map OSM elements onto substation and transmission-line records."""
        records: list[NormalizedRecord] = []
        rejected = 0
        filtered = 0
        warnings = list(document.warnings)

        for element in document.records:
            power_type = element["power"]
            try:
                if power_type == "substation":
                    record = self._normalize_substation(element)
                elif power_type == "line":
                    record = self._normalize_line(element)
                else:
                    filtered += 1
                    continue
            except (ValueError, TypeError, KeyError) as exc:
                rejected += 1
                warnings.append(f"{element.get('_locator')}: {type(exc).__name__}: {exc}")
                continue

            if record is None:
                # Out of scope rather than broken: a distribution circuit or an
                # element with no usable location.
                filtered += 1
                continue
            records.append(record)

        logger.info(
            "osm_power.normalized",
            substations=sum(1 for r in records if r.entity_type == "substation"),
            lines=sum(1 for r in records if r.entity_type == "transmission_line"),
            filtered=filtered,
            rejected=rejected,
        )
        return NormalizationResult(
            records=records, rejected=rejected, filtered=filtered, warnings=warnings
        )

    def _normalize_substation(self, element: dict[str, Any]) -> NormalizedRecord | None:
        """Normalize one substation element."""
        tags = element["tags"]
        lat, lon = element.get("lat"), element.get("lon")
        if lat is None or lon is None:
            # `out center` supplies a centroid for ways and relations; an element
            # without one cannot be placed and is useless as spatial evidence.
            return None

        voltages = parse_voltage_list(tags.get("voltage"))
        native_id = f"{element['osm_type']}/{element['osm_id']}"
        locator = element["_locator"]

        fields = [
            ExtractedField(
                name="max_voltage_kv",
                value=voltages[0] if voltages else None,
                raw_text=tags.get("voltage"),
                raw_unit="V",
                normalized_unit="kV",
                assertion_class=(AssertionClass.REPORTED if voltages else AssertionClass.UNKNOWN),
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                confidence=0.8 if voltages else 0.0,
                locator=f"{locator}.tags.voltage",
            )
        ]
        if operator := tags.get("operator"):
            fields.append(
                ExtractedField(
                    name="operator_name",
                    value=operator,
                    raw_text=operator,
                    assertion_class=AssertionClass.REPORTED,
                    extraction_method=ExtractionMethod.STRUCTURED_FEED,
                    confidence=0.75,
                    locator=f"{locator}.tags.operator",
                )
            )

        return NormalizedRecord(
            entity_type="substation",
            source_native_id=native_id,
            payload={
                "source_native_id": native_id,
                "name": tags.get("name"),
                "operator_name": tags.get("operator"),
                "max_voltage_kv": voltages[0] if voltages else None,
                "voltages_kv": [str(v) for v in voltages],
                "substation_function": tags.get("substation"),
                "status": _lifecycle_status(tags),
                "latitude": lat,
                "longitude": lon,
                "osm_url": f"https://www.openstreetmap.org/{element['osm_type']}/{element['osm_id']}",
                "locator": locator,
            },
            fields=fields,
            geometry_wkt=f"POINT({lon} {lat})",
        )

    def _normalize_line(self, element: dict[str, Any]) -> NormalizedRecord | None:
        """Normalize one transmission-line element, dropping distribution circuits."""
        tags = element["tags"]
        voltages = parse_voltage_list(tags.get("voltage"))
        if not voltages or voltages[0] < self.min_voltage_kv:
            return None

        native_id = f"{element['osm_type']}/{element['osm_id']}"
        lat, lon = element.get("lat"), element.get("lon")

        return NormalizedRecord(
            entity_type="transmission_line",
            source_native_id=native_id,
            payload={
                "source_native_id": native_id,
                "name": tags.get("name") or tags.get("ref"),
                "operator_name": tags.get("operator"),
                "voltage_kv": voltages[0],
                "circuit_count": _int_or_none(tags.get("circuits")),
                "status": _lifecycle_status(tags),
                "latitude": lat,
                "longitude": lon,
                "osm_url": f"https://www.openstreetmap.org/{element['osm_type']}/{element['osm_id']}",
                "locator": element["_locator"],
            },
            fields=[
                ExtractedField(
                    name="voltage_kv",
                    value=voltages[0],
                    raw_text=tags.get("voltage"),
                    raw_unit="V",
                    normalized_unit="kV",
                    assertion_class=AssertionClass.REPORTED,
                    extraction_method=ExtractionMethod.STRUCTURED_FEED,
                    confidence=0.8,
                    locator=f"{element['_locator']}.tags.voltage",
                )
            ],
            # `out center` gives only a centroid for ways, so line geometry is
            # represented by that point rather than a full polyline. Recorded as a
            # known limitation: distance-to-line calculations are approximate.
            geometry_wkt=f"POINT({lon} {lat})" if lat is not None and lon is not None else None,
        )


def _lifecycle_status(tags: dict[str, Any]) -> str:
    """Derive a lifecycle status from OSM lifecycle prefixes and tags."""
    for key in ("construction", "proposed", "planned", "disused", "abandoned"):
        if tags.get(key) or tags.get(f"{key}:power"):
            return key
    return str(tags.get("status") or "operational")


def _int_or_none(value: Any) -> int | None:
    """Coerce a tag value to int, returning ``None`` when it is not numeric."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


__all__ = [
    "HYPERSCALE_RELEVANT_KV",
    "TRANSMISSION_VOLTAGE_KV",
    "OsmPowerConnector",
]
