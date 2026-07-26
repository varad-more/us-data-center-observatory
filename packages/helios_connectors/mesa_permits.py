"""Connector for City of Mesa commercial building permits (Socrata).

The public view exposes permit number, type, property address, status, and
dates — no coordinates, valuation, or applicant. Helios therefore:

* ingests ``COM`` (commercial) permits only, because residential volume drowns
  the signal and is mostly irrelevant to hyperscale campuses;
* matches permits onto parcels by normalized address after assessor data exists;
* emits ``grading_or_construction_permit`` evidence for issued/in-review
  commercial work, which is a Stage 4 construction signal when it lands on a
  candidate site.

Street filters keep live pulls bounded to the East Valley corridors that
already contain assessor-classified data-centre parcels.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

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

DATASET_URL = "https://data.mesaaz.gov/resource/a2ui-hcuj.json"
PAGE_SIZE = 500

DEFAULT_STREET_FILTERS: tuple[str, ...] = (
    "SIGNAL BUTTE",
    "ELLSWORTH",
    "HOLMES",
    "EVERTON",
    "ELLIOT",
)


class MesaBuildingPermitsConnector(BaseConnector):
    """Reads commercial building permits from Mesa's Socrata open-data portal."""

    def __init__(
        self,
        *,
        http_client: PoliteHttpClient | None = None,
        settings: Settings | None = None,
        street_filters: tuple[str, ...] | None = None,
        permit_types: tuple[str, ...] = ("COM",),
        max_rows: int = 2000,
    ) -> None:
        """Initialise the connector.

        Args:
            http_client: Shared HTTP client.
            settings: Configuration override.
            street_filters: Case-insensitive substrings for ``property_address``.
            permit_types: Socrata ``permit_type`` values to keep (default COM).
            max_rows: Hard cap on rows fetched per run.
        """
        super().__init__(http_client=http_client, settings=settings)
        self.street_filters = street_filters or DEFAULT_STREET_FILTERS
        self.permit_types = permit_types
        self.max_rows = max_rows

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="mesa-building-permits",
            source_slug="mesa-building-permits",
            name="City of Mesa Building Permits",
            agency="City of Mesa",
            jurisdiction="Mesa, Arizona",
            category=SourceCategory.MUNICIPAL_PLANNING,
            access_method=AccessMethod.SOCRATA,
            base_url=DATASET_URL,
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.IMPLEMENTED,
            update_frequency="daily",
            rate_limit_per_second=2.0,
            license_name="City of Mesa open data",
            license_url="https://data.mesaaz.gov/",
            robots_policy_status="allowed",
            geographic_coverage="Mesa, Arizona (street-filtered for East Valley)",
            historical_coverage="Permits from approximately 2015 onward.",
            reliability_score=0.75,
            known_schema_issues=(
                "No coordinates, valuation, work description, or applicant. Matching "
                "is address-string only via helios_geospatial.addresses."
            ),
        )

    def health_check(self) -> HealthCheckResult:
        """Probe the dataset with a one-row query."""
        started = utcnow()
        try:
            response = self.http.get(DATASET_URL, params={"$limit": "1"})
            payload = json.loads(response.content)
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, checked_at=started, message=f"{type(exc).__name__}: {exc}"
            )
        healthy = response.status_code == 200 and isinstance(payload, list)
        return HealthCheckResult(
            healthy=healthy,
            checked_at=started,
            latency_ms=response.elapsed_ms,
            http_status=response.status_code,
            detail={"sample_rows": len(payload) if isinstance(payload, list) else 0},
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Discover one logical document covering the street-filtered COM query."""
        del date_range
        where = self._where_clause()
        return DiscoveryResult(
            items=[
                SourceItem(
                    source_native_id=f"mesa-permits:{short_hash(where)}",
                    url=f"{DATASET_URL}?{urlencode({'$where': where})}",
                    title="Mesa commercial building permits (street-filtered)",
                    document_type="mesa_permits_json",
                    hints={"where": where},
                )
            ]
        )

    def fetch(self, item: SourceItem) -> FetchResult:
        """Page through Socrata results and merge into one JSON array."""
        where = str(item.hints.get("where") or self._where_clause())
        rows: list[dict[str, Any]] = []
        offset = 0
        last_status = 200
        last_headers: dict[str, str] = {}
        try:
            while offset < self.max_rows:
                params = {
                    "$where": where,
                    "$limit": str(min(PAGE_SIZE, self.max_rows - offset)),
                    "$offset": str(offset),
                    "$order": "opened_date DESC",
                }
                response = self.http.get(DATASET_URL, params=params)
                last_status = response.status_code
                last_headers = dict(response.headers)
                page = json.loads(response.content)
                if not isinstance(page, list):
                    return FetchResult(document=None, error="Expected a JSON array from Socrata")
                if not page:
                    break
                rows.extend(page)
                if len(page) < PAGE_SIZE:
                    break
                offset += len(page)
        except Exception as exc:
            return FetchResult(document=None, error=f"{type(exc).__name__}: {exc}")

        body = json.dumps(rows, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return FetchResult(
            document=RawDocument(
                item=item,
                payload=body,
                mime_type="application/json",
                retrieved_at=utcnow(),
                http_status=last_status,
                headers=last_headers,
                etag=last_headers.get("etag"),
            )
        )

    def parse(self, document: RawDocument) -> ParseResult:
        """Parse a Socrata page into source-native permit rows."""
        try:
            rows = json.loads(document.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return ParseResult(document=None, error=f"Invalid Mesa permits JSON: {exc}")
        if not isinstance(rows, list):
            return ParseResult(document=None, error="Expected a JSON array from Socrata")
        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="mesa_permits_json",
                records=rows,
                field_signature=self.field_signature(rows),
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Map commercial permits onto Helios permit entities."""
        records: list[NormalizedRecord] = []
        rejected = 0
        filtered = 0
        for index, row in enumerate(document.records):
            permit_type = str(row.get("permit_type") or "").upper()
            if permit_type not in {t.upper() for t in self.permit_types}:
                filtered += 1
                continue
            try:
                records.append(self._normalize_row(row, index=index))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("mesa.normalize_rejected", error=str(exc), index=index)
                rejected += 1
        # Empty trailing pages are normal once offset exceeds the result set.
        if not document.records:
            filtered += 0
        return NormalizationResult(records=records, rejected=rejected, filtered=filtered)

    def _normalize_row(self, row: dict[str, Any], *, index: int) -> NormalizedRecord:
        """Normalize one Socrata permit row."""
        permit_number = str(row["permit_number"])
        address = str(row.get("property_address") or "").strip()
        if not address:
            raise ValueError(f"{permit_number} missing property_address")

        opened = _parse_date(row.get("opened_date"))
        issued = _parse_date(row.get("issued_date"))
        status_date = _parse_date(row.get("status_date"))
        observed = issued or status_date or opened
        if observed is None:
            raise ValueError(f"{permit_number} has no usable date")

        permit_type = str(row.get("permit_type") or "COM").upper()
        status = str(row.get("status_category") or row.get("status") or "")
        category = (
            PermitCategory.BUILDING_COMMERCIAL
            if permit_type == "COM"
            else PermitCategory.BUILDING_RESIDENTIAL
        )

        fields = [
            ExtractedField(
                name="permit_number",
                value=permit_number,
                confidence=1.0,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$[{index}].permit_number",
            ),
            ExtractedField(
                name="property_address",
                value=address,
                confidence=0.95,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$[{index}].property_address",
            ),
            ExtractedField(
                name="permit_type",
                value=permit_type,
                confidence=1.0,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$[{index}].permit_type",
            ),
        ]

        summary = (
            f"City of Mesa commercial building permit {permit_number} at {address}"
            + (f", opened {opened.isoformat()}" if opened else "")
            + (f", status: {status}" if status else "")
            + ". Matched to parcels by normalized address; no coordinates in source."
        )

        evidence = [
            EvidenceItem(
                kind=str(StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT),
                summary=summary,
                observed_at=observed,
                confidence=0.75,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$[{index}]",
                snippet=f"{permit_number}; {permit_type}; {address}; {status}",
                fields=fields,
            )
        ]

        return NormalizedRecord(
            entity_type="permit",
            source_native_id=permit_number,
            payload={
                "source_native_id": permit_number,
                "permit_number": permit_number,
                "category": str(category),
                "permit_type_raw": permit_type,
                "description": status or f"Mesa {permit_type} permit",
                "status": status or None,
                "issuing_authority": "City of Mesa",
                "jurisdiction": "Mesa",
                "applied_date": opened,
                "issued_date": issued,
                "address_raw": address,
                "latitude": None,
                "longitude": None,
                "attributes": {
                    "status_date": status_date.isoformat() if status_date else None,
                    "property_address": address,
                    "permit_type": permit_type,
                },
            },
            fields=fields,
            evidence=evidence,
        )

    def _where_clause(self) -> str:
        """Build the SoQL WHERE clause for commercial permits on target streets."""
        type_list = ", ".join(f"'{t}'" for t in self.permit_types)
        street_clause = " OR ".join(
            f"upper(property_address) like '%{street.upper()}%'" for street in self.street_filters
        )
        return f"permit_type in ({type_list}) AND ({street_clause})"


def _parse_date(value: object) -> date | None:
    """Parse a Socrata ISO datetime/date string."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text[:10])


__all__ = ["DEFAULT_STREET_FILTERS", "MesaBuildingPermitsConnector"]
