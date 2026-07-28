"""Connector for EPA ECHO Clean Air Act facility records.

Backup-generator air permits are among the strongest non-spatial public signals
that a large IT load is present or imminent. ECHO exposes ICIS-Air facilities
through a two-step REST API:

1. ``air_rest_services.get_facilities`` validates the query and returns a
   short-lived ``QueryID``.
2. ``air_rest_services.get_qid`` pages facility rows for that QueryID.

Helios keeps facilities that look like data-centre hosting and/or emergency
generation, and emits ``backup_generator_air_permit`` evidence when generator
program text or hosting NAICS supports that reading. Ordinary industrial air
permits are counted as ``filtered``, not rejected.

Two query modes
---------------
*City mode* enumerates municipalities, one round trip each. It was how the
study area was read, and it is the reason the study area was six cities: a
national sweep would need thousands of requests against an API that throttles
at roughly 300 per hour.

*Industry mode* uses ECHO's ``p_ncs`` NAICS filter instead, which returns every
matching facility in the country in one request. Note that ``p_ncs`` is the
parameter that works; ``p_naics`` is accepted and silently ignored, returning
the unfiltered result set — a filter that appears to work and does not.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from helios_common.config import Settings
from helios_common.hashing import short_hash
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
    EvidenceItem,
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
from helios_domain.ontology import PermitCategory, StageEvidenceKind

logger = get_logger(__name__)

CONNECTOR_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"

GET_FACILITIES_URL = "https://echodata.epa.gov/echo/air_rest_services.get_facilities"
GET_QID_URL = "https://echodata.epa.gov/echo/air_rest_services.get_qid"
METADATA_URL = "https://echodata.epa.gov/echo/air_rest_services.metadata"

DEFAULT_CITIES: tuple[str, ...] = (
    "Mesa",
    "Chandler",
    "Tempe",
    "Gilbert",
    "Queen Creek",
    "Apache Junction",
)

HOSTING_NAICS_QUERY: tuple[str, ...] = ("518210", "541513")
"""NAICS codes ECHO is asked to filter on in industry mode.

``518210`` is "Computing Infrastructure Providers, Data Processing, Web Hosting,
and Related Services"; ``541513`` is the computer-facilities-management code
that carried part of the same activity before the 2022 NAICS revision. Both are
much broader than "data centre" - payroll processors and streaming services sit
under 518210 too - so this narrows the *query*, not the *conclusion*. The
classification that follows is unchanged.
"""

# ObjectName column IDs from ECHO Air metadata (echor / EPA docs).
# Defaults always include RegistryID, FacName, FacLat, FacLong.
QCOLUMNS = "1,2,3,4,5,7,8,14,15,16,17,18,19,23,24,25"

_HOSTING_NAICS = {"518210", "541513", "5182"}
_HOSTING_NAME_PATTERN = re.compile(
    r"data\s*cent|colocation|co-location|colo\b|hosting|server farm",
    re.IGNORECASE,
)


class EpaEchoAirConnector(BaseConnector):
    """Reads CAA air facilities from EPA ECHO, by city or by industry code."""

    def __init__(
        self,
        *,
        http_client: PoliteHttpClient | None = None,
        settings: Settings | None = None,
        cities: tuple[str, ...] | None = None,
        state: str | None = "AZ",
        naics_codes: tuple[str, ...] | None = None,
    ) -> None:
        """Initialise the connector in either city mode or industry mode.

        City mode enumerates municipalities and costs one round trip each, which
        is why the study area was six cities: it does not scale to a country.
        Industry mode asks ECHO's ``p_ncs`` parameter for the hosting NAICS codes
        directly and covers the whole United States in a single request.

        Args:
            http_client: Shared HTTP client.
            settings: Configuration override.
            cities: City names to query within ``state``. Ignored in industry mode.
            state: Two-letter state code, or ``None`` in industry mode for nationwide.
            naics_codes: Setting this selects industry mode.
        """
        super().__init__(http_client=http_client, settings=settings)
        self.cities = cities or DEFAULT_CITIES
        self.state = state
        self.naics_codes = tuple(naics_codes) if naics_codes else ()

    @property
    def is_industry_mode(self) -> bool:
        """Whether the connector queries by NAICS rather than by city."""
        return bool(self.naics_codes)

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="epa-echo-air-facilities",
            source_slug="epa-echo-air-facilities",
            name="EPA ECHO Air Facility Records",
            agency="United States Environmental Protection Agency",
            jurisdiction="United States",
            category=SourceCategory.ENVIRONMENTAL,
            access_method=AccessMethod.REST_JSON,
            base_url=GET_FACILITIES_URL,
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.IMPLEMENTED,
            update_frequency="weekly",
            rate_limit_per_second=1.0,
            license_name="US Government public domain",
            license_url="https://www.epa.gov/privacy/privacy-and-security-notice",
            robots_policy_status="allowed",
            geographic_coverage=(
                "Nationwide. Queried either per city within a study region, or "
                "nationwide by hosting NAICS code."
            ),
            historical_coverage="Active and historical Clean Air Act permitted facilities.",
            reliability_score=0.85,
            known_schema_issues=(
                "Two-step API: get_facilities returns QueryID for get_qid. Facility "
                "coordinates are sometimes geocoded rather than surveyed. Public API "
                "throttles at roughly 300 requests/hour."
            ),
        )

    def health_check(self) -> HealthCheckResult:
        """Probe the metadata endpoint without running a facility query."""
        started = utcnow()
        try:
            response = self.http.get(METADATA_URL, params={"output": "JSON"})
            payload = json.loads(response.content)
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, checked_at=started, message=f"{type(exc).__name__}: {exc}"
            )

        error = _echo_error_message(payload)
        # Metadata occasionally returns only the throttle notice with HTTP 200/429.
        healthy = response.status_code < 400 and (
            "Results" in payload and (error is None or "throttle" in error.lower())
        )
        return HealthCheckResult(
            healthy=healthy or response.status_code == 200,
            checked_at=started,
            latency_ms=response.elapsed_ms,
            http_status=response.status_code,
            message=error,
            detail={"has_results": "Results" in payload},
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Discover the one logical document this connector's query produces."""
        del date_range
        scope = self.state or "US"

        if self.is_industry_mode:
            naics_label = ",".join(self.naics_codes)
            return DiscoveryResult(
                items=[
                    SourceItem(
                        source_native_id=f"echo:air:naics:{scope.lower()}:"
                        f"{short_hash(naics_label)}",
                        url=GET_FACILITIES_URL,
                        title=f"ECHO air facilities ({scope}: NAICS {naics_label})",
                        document_type="echo_air_facilities_json",
                        hints={"naics": list(self.naics_codes), "state": self.state},
                    )
                ]
            )

        city_label = ",".join(self.cities)
        return DiscoveryResult(
            items=[
                SourceItem(
                    source_native_id=f"echo:air:{scope.lower()}:{short_hash(city_label)}",
                    url=GET_FACILITIES_URL,
                    title=f"ECHO air facilities ({scope}: {city_label})",
                    document_type="echo_air_facilities_json",
                    hints={"cities": list(self.cities), "state": self.state},
                )
            ]
        )

    def fetch(self, item: SourceItem) -> FetchResult:
        """Fetch facility rows for the discovered query.

        Industry mode is one request; city mode is one per city. Both funnel into
        the same merged payload shape so the parser does not need to know which
        query produced it.
        """
        naics = [str(code) for code in (item.hints.get("naics") or self.naics_codes)]
        state_hint = item.hints.get("state", self.state)
        state = str(state_hint) if state_hint else None

        facilities: list[dict[str, Any]] = []
        query_ids: list[str] = []
        warnings: list[str] = []
        query_note: dict[str, Any]

        if naics:
            try:
                facilities, qid, warning = self._fetch_query(
                    {"p_ncs": ",".join(naics)}, state, label=f"NAICS {','.join(naics)}"
                )
            except Exception as exc:
                return FetchResult(
                    document=None,
                    error=f"ECHO fetch failed for NAICS query: {type(exc).__name__}: {exc}",
                )
            if warning:
                warnings.append(warning)
            if qid:
                query_ids.append(qid)
            query_note = {"state": state, "naics": naics, "warnings": warnings}
        else:
            cities = [str(city) for city in (item.hints.get("cities") or self.cities)]
            for city in cities:
                try:
                    city_rows, qid, warning = self._fetch_query({"p_city": city}, state, label=city)
                except Exception as exc:
                    return FetchResult(
                        document=None,
                        error=f"ECHO fetch failed for {city}: {type(exc).__name__}: {exc}",
                    )
                if warning:
                    warnings.append(warning)
                if qid:
                    query_ids.append(qid)
                facilities.extend(city_rows)
            query_note = {"state": state, "cities": cities, "warnings": warnings}

        if not facilities and warnings:
            return FetchResult(document=None, error="; ".join(warnings))

        payload = {
            "Results": {
                "Message": "Working",
                "QueryRows": str(len(facilities)),
                "QueryID": ",".join(query_ids) or "merged",
                "PageNo": "1",
                "Facilities": facilities,
            },
            "_helios_query": query_note,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return FetchResult(
            document=RawDocument(
                item=item,
                payload=body,
                mime_type="application/json",
                retrieved_at=utcnow(),
                http_status=200,
                headers={"content-type": "application/json"},
            )
        )

    def _fetch_query(
        self,
        selector: dict[str, str],
        state: str | None,
        *,
        label: str,
    ) -> tuple[list[dict[str, Any]], str | None, str | None]:
        """Run one narrowing through the two-step ECHO API.

        Args:
            selector: The narrowing parameter, e.g. ``{"p_city": "Mesa"}`` or
                ``{"p_ncs": "518210,541513"}``. ``p_ncs`` is the documented NAICS
                filter; ``p_naics`` is silently ignored by ECHO and returns every
                row in scope, which is the worst kind of wrong answer.
            state: Two-letter state code, or ``None`` for nationwide.
            label: What to name this query in a warning.

        Returns:
            Facility rows, the QueryID if one was issued, and any warning.
        """
        params = {
            "output": "JSON",
            "p_act": "Y",
            "responseset": "1",
            "qcolumns": QCOLUMNS,
            **selector,
        }
        if state:
            params["p_st"] = state
        query_response = self.http.get(GET_FACILITIES_URL, params=params)
        query_payload = json.loads(query_response.content)
        error = _echo_error_message(query_payload)
        results = query_payload.get("Results") or {}
        throttled = query_response.status_code == 429 or (
            error is not None and "throttle" in error.lower() and "QueryID" not in results
        )
        if throttled:
            return [], None, f"{label}: throttled by ECHO ({error})"

        query_id = results.get("QueryID")
        # Some responses embed the first page of facilities directly.
        embedded = list(results.get("Facilities") or [])
        if embedded:
            return embedded, str(query_id) if query_id else None, error

        if not query_id:
            return [], None, f"{label}: no QueryID ({error or 'empty Results'})"

        page_response = self.http.get(
            GET_QID_URL,
            params={
                "output": "JSON",
                "qid": query_id,
                "pageno": "1",
                "qcolumns": QCOLUMNS,
            },
        )
        page_payload = json.loads(page_response.content)
        page_error = _echo_error_message(page_payload)
        page_results = page_payload.get("Results") or {}
        facilities = list(page_results.get("Facilities") or [])
        return facilities, str(query_id), page_error or error

    def parse(self, document: RawDocument) -> ParseResult:
        """Parse an ECHO facilities JSON document."""
        try:
            payload = json.loads(document.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ParseResult(document=None, error=f"Invalid ECHO JSON: {exc}")

        results = payload.get("Results") or {}
        facilities = list(results.get("Facilities") or [])
        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="echo_air_facilities_json",
                records=facilities,
                field_signature=self.field_signature(facilities),
                warnings=list((payload.get("_helios_query") or {}).get("warnings") or []),
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Keep hosting/generator-relevant facilities; filter the rest."""
        records: list[NormalizedRecord] = []
        rejected = 0
        filtered = 0
        observed = date.today()

        for index, row in enumerate(document.records):
            try:
                decision = self._classify_facility(row)
                if decision == "filter":
                    filtered += 1
                    continue
                normalized = self._normalize_facility(row, index=index, observed_at=observed)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("echo.normalize_rejected", error=str(exc), index=index)
                rejected += 1
                continue
            records.append(normalized)

        return NormalizationResult(
            records=records,
            rejected=rejected,
            filtered=filtered,
            warnings=list(document.warnings),
        )

    def _classify_facility(self, row: dict[str, Any]) -> str:
        """Return ``keep`` or ``filter`` for a facility row.

        Ordinary industrial air permits are extremely common. Helios only keeps
        facilities that look like data-processing / hosting sites (NAICS or name).
        Generator program text strengthens the evidence summary but is not enough
        alone - a municipal well backup engine is not a campus signal.
        """
        naics = _codes(row.get("FacNAICSCodes") or row.get("NAICSCodes"))
        name = str(row.get("FacName") or row.get("AIRName") or "")
        hosting = bool(naics & _HOSTING_NAICS) or bool(_HOSTING_NAME_PATTERN.search(name))
        return "keep" if hosting else "filter"

    def _normalize_facility(
        self, row: dict[str, Any], *, index: int, observed_at: date
    ) -> NormalizedRecord:
        """Map one ECHO facility onto a permit + generator evidence."""
        registry_id = str(row.get("RegistryID") or row.get("SourceID") or f"row-{index}")
        source_id = str(row.get("SourceID") or registry_id)
        name = str(row.get("FacName") or row.get("AIRName") or "Unknown facility")
        lat = _float_or_none(row.get("FacLat") or row.get("Latitude"))
        lon = _float_or_none(row.get("FacLong") or row.get("Longitude"))
        city = str(row.get("FacCity") or row.get("AIRCity") or "")
        street = str(row.get("FacStreet") or row.get("AIRStreet") or "")
        programs = str(row.get("AIRPrograms") or "")
        naics = sorted(_codes(row.get("FacNAICSCodes")))

        geometry = f"POINT({lon} {lat})" if lat is not None and lon is not None else None
        address = ", ".join(part for part in (street, city, "AZ") if part)

        fields = [
            ExtractedField(
                name="registry_id",
                value=registry_id,
                confidence=1.0,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$.Results.Facilities[{index}].RegistryID",
            ),
            ExtractedField(
                name="facility_name",
                value=name,
                confidence=0.95,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$.Results.Facilities[{index}].FacName",
            ),
            ExtractedField(
                name="naics",
                value=",".join(naics),
                confidence=0.9,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$.Results.Facilities[{index}].FacNAICSCodes",
            ),
        ]

        summary = (
            f"EPA ECHO lists {name} as a Clean Air Act facility"
            + (f" (NAICS {', '.join(naics)})" if naics else "")
            + ". Program text and/or hosting NAICS are consistent with backup "
            "generation at a data-processing site. Coordinates may be geocoded."
        )
        if programs:
            summary += f" Programs: {programs}."

        evidence = [
            EvidenceItem(
                kind=str(StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT),
                summary=summary,
                observed_at=observed_at,
                confidence=0.8,
                assertion_class=AssertionClass.EXTRACTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$.Results.Facilities[{index}]",
                snippet=f"{name}; {programs or 'no program text'}",
                fields=fields,
                is_standing_condition=True,
            )
        ]

        return NormalizedRecord(
            entity_type="permit",
            source_native_id=source_id,
            payload={
                "source_native_id": source_id,
                "permit_number": source_id,
                "category": str(PermitCategory.BACKUP_GENERATOR),
                "permit_type_raw": programs or "ECHO air facility",
                "description": name,
                "status": row.get("AIRStatus") or row.get("FacStatus"),
                "issuing_authority": "US EPA / ICIS-Air (via ECHO)",
                "jurisdiction": city or "Arizona",
                "applied_date": None,
                "issued_date": None,
                "address_raw": address or None,
                "latitude": lat,
                "longitude": lon,
                "attributes": {
                    "registry_id": registry_id,
                    "naics": naics,
                    "programs": programs,
                    "facility_name": name,
                },
            },
            fields=fields,
            evidence=evidence,
            geometry_wkt=geometry,
        )


def _echo_error_message(payload: dict[str, Any]) -> str | None:
    """Extract an ECHO Results.Error.ErrorMessage if present."""
    results = payload.get("Results")
    if not isinstance(results, dict):
        return None
    error = results.get("Error")
    if isinstance(error, dict):
        message = error.get("ErrorMessage")
        return str(message) if message else None
    return None


def _codes(value: object) -> set[str]:
    """Split a semicolon/comma-delimited code string."""
    if value is None:
        return set()
    parts = re.split(r"[;,]\s*", str(value).strip())
    return {part.strip() for part in parts if part.strip()}


def _float_or_none(value: object) -> float | None:
    """Parse a float from ECHO's stringly-typed coordinates."""
    if value is None or value == "":
        return None
    if isinstance(value, str | int | float):
        return float(value)
    return None


__all__ = ["DEFAULT_CITIES", "EpaEchoAirConnector"]
