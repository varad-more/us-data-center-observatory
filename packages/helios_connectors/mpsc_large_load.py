"""Michigan large-load regulatory disclosure connector.

The first supported record is MPSC Case U-21990: an official Commission
disclosure that names the utility, customer, township and contracted data-centre
load. The page provides township-level location only, so this connector emits a
regulatory filing with no geometry. A downstream consumer must not turn
"Saline Township" into an exact facility point.

Discovery is deliberately curated rather than pretending the MPSC eDockets
interface is a structured statewide feed. Additional official disclosure pages
can be added as their document shapes receive parser fixtures and contract
tests.
"""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from helios_common.config import Settings
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
    NormalizationResult,
    NormalizedRecord,
    ParsedDocument,
    ParseResult,
    RawDocument,
    SourceItem,
)
from helios_domain.ontology import PermitCategory, StageEvidenceKind

CONNECTOR_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"

MPSC_U_21990_URL = (
    "https://www.michigan.gov/mpsc/commission/events/2025/12/18/~/link.aspx"
    "?_id=5F5E5CA34D71466696AB507F9571E9FC&_z=z"
)
MPSC_U_21990_DATE = date(2025, 12, 18)

_LOAD_PATTERN = re.compile(
    r"1,383-\s*megawatt \(MW\) data center in Saline Township",
    re.IGNORECASE,
)
_DOCKET_PATTERN = re.compile(r"Case No\. U-21990", re.IGNORECASE)


class MpscLargeLoadConnector(BaseConnector):
    """Read curated official MPSC large-load decision disclosures."""

    def __init__(
        self,
        *,
        http_client: PoliteHttpClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialise the connector."""
        super().__init__(http_client=http_client, settings=settings)

    def get_metadata(self) -> ConnectorMetadata:
        """Return the source and connector description."""
        return ConnectorMetadata(
            slug="mpsc-large-load-contracts",
            source_slug="mpsc-large-load-contracts",
            name="Michigan PSC Large-Load Contract Disclosures",
            agency="Michigan Public Service Commission",
            jurisdiction="Michigan",
            category=SourceCategory.UTILITY_AND_REGULATORY,
            access_method=AccessMethod.HTML_PAGE,
            base_url=MPSC_U_21990_URL,
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.IMPLEMENTED,
            update_frequency="event-driven",
            rate_limit_per_second=0.5,
            geographic_coverage="Michigan; currently one site-specific order in Washtenaw County",
            historical_coverage=(
                "Curated official Commission disclosures from December 2025 onward."
            ),
            reliability_score=1.0,
            known_schema_issues=(
                "Commission news pages are prose rather than a docket API. Discovery is "
                "a reviewed URL list, and each new page shape requires a recorded fixture "
                "and parser contract before it is published."
            ),
            notes=(
                "The first record is Case U-21990. It reports a contracted load and "
                "township, not a street address or parcel, so Helios publishes no geometry."
            ),
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Return supported official decision disclosures within the date range."""
        items: list[SourceItem] = []
        if date_range.contains(MPSC_U_21990_DATE):
            items.append(
                SourceItem(
                    source_native_id="mpsc:U-21990:2025-12-18",
                    url=MPSC_U_21990_URL,
                    title=(
                        "MPSC approval of DTE Electric contracts for the "
                        "Saline Township data center"
                    ),
                    document_type="mpsc_large_load_disclosure_html",
                    published_date=MPSC_U_21990_DATE,
                    effective_date=MPSC_U_21990_DATE,
                )
            )
        return DiscoveryResult(items=items)

    def fetch(self, item: SourceItem) -> FetchResult:
        """Fetch one official Commission disclosure page."""
        try:
            response = self.http.get(item.url)
        except Exception as exc:
            return FetchResult(document=None, error=f"{type(exc).__name__}: {exc}")
        if response.status_code >= 400:
            return FetchResult(
                document=None,
                error=f"MPSC returned HTTP {response.status_code} for {item.url}",
            )
        return FetchResult(
            document=RawDocument(
                item=item,
                payload=response.content,
                mime_type=response.mime_type,
                retrieved_at=utcnow(),
                http_status=response.status_code,
                headers=response.headers,
                etag=response.etag,
                last_modified=response.last_modified,
            )
        )

    def parse(self, document: RawDocument) -> ParseResult:
        """Extract the supported U-21990 disclosure from Commission HTML."""
        try:
            html = document.payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            return ParseResult(document=None, error=f"Invalid MPSC HTML encoding: {exc}")

        text = " ".join(BeautifulSoup(html, "lxml").stripped_strings)
        load_match = _LOAD_PATTERN.search(text)
        docket_match = _DOCKET_PATTERN.search(text)
        required_phrases = (
            "conditionally approved",
            "DTE Electric Co.",
            "Washtenaw County data center",
            "Green Chile Ventures LLC",
            "Oracle Corp.",
        )
        missing_phrases = [phrase for phrase in required_phrases if phrase not in text]
        if load_match is None or docket_match is None or missing_phrases:
            return ParseResult(
                document=None,
                error=(
                    "MPSC U-21990 disclosure no longer contains every approval, party, "
                    "location, contracted-load, and docket phrase required by parser 0.1.0"
                ),
            )

        sentence_start = text.rfind(".", 0, load_match.start()) + 1
        sentence_end = text.find(".", load_match.end())
        snippet = text[sentence_start : sentence_end + 1].strip()

        record = {
            "docket_number": "U-21990",
            "decision_date": MPSC_U_21990_DATE.isoformat(),
            "status": "conditionally_approved",
            "utility_name": "DTE Electric Co.",
            "customer_name": "Green Chile Ventures LLC",
            "parent_company_name": "Oracle Corp.",
            "project_type": "data_center",
            "reported_load_mw": 1383.0,
            "reported_load_raw": load_match.group(0),
            "location_name": "Saline Township",
            "county_name": "Washtenaw County",
            "state_code": "MI",
            "location_precision": "township",
            "snippet": snippet,
        }
        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="mpsc_large_load_disclosure_html",
                text=text,
                records=[record],
                field_signature=self.field_signature([record]),
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Normalize U-21990 into a filing and one atomic evidence record."""
        if len(document.records) != 1:
            return NormalizationResult(
                records=[],
                rejected=len(document.records),
                error="Expected exactly one supported MPSC disclosure record",
            )

        row = document.records[0]
        observed_at = date.fromisoformat(str(row["decision_date"]))
        fields = [
            ExtractedField(
                name="docket_number",
                value=row["docket_number"],
                raw_text="Case No. U-21990",
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; docket reference",
            ),
            ExtractedField(
                name="reported_load_mw",
                value=row["reported_load_mw"],
                raw_text=str(row["reported_load_raw"]),
                raw_unit="MW",
                normalized_unit="MW",
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; approval conditions",
            ),
            ExtractedField(
                name="utility_name",
                value=row["utility_name"],
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; approval conditions",
            ),
            ExtractedField(
                name="customer_name",
                value=row["customer_name"],
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; approval conditions",
            ),
            ExtractedField(
                name="parent_company_name",
                value=row["parent_company_name"],
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; approval conditions",
            ),
            ExtractedField(
                name="location_name",
                value=row["location_name"],
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; approval conditions",
            ),
            ExtractedField(
                name="county_name",
                value=row["county_name"],
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.REGEX,
                confidence=1.0,
                locator="official disclosure; introductory paragraph",
            ),
            ExtractedField(
                name="state_code",
                value=row["state_code"],
                assertion_class=AssertionClass.CALCULATED,
                extraction_method=ExtractionMethod.PATTERN_RULE,
                confidence=1.0,
                locator="Michigan Public Service Commission jurisdiction",
            ),
            ExtractedField(
                name="location_precision",
                value="township",
                assertion_class=AssertionClass.CALCULATED,
                extraction_method=ExtractionMethod.PATTERN_RULE,
                confidence=1.0,
                locator="most specific location named by source",
            ),
        ]
        evidence = EvidenceItem(
            kind=str(StageEvidenceKind.LARGE_LOAD_SERVICE_CONTRACT),
            summary=(
                "MPSC conditionally approved DTE Electric service contracts for "
                "Green Chile Ventures' reported 1,383 MW data center in Saline Township."
            ),
            snippet=str(row["snippet"]),
            locator="official disclosure; approval conditions",
            observed_at=observed_at,
            assertion_class=AssertionClass.EXTRACTED,
            extraction_method=ExtractionMethod.REGEX,
            confidence=1.0,
            fields=fields,
        )
        return NormalizationResult(
            records=[
                NormalizedRecord(
                    entity_type="permit",
                    source_native_id="mpsc:U-21990:2025-12-18",
                    payload={
                        "source_native_id": "mpsc:U-21990:2025-12-18",
                        "permit_number": row["docket_number"],
                        "category": str(PermitCategory.UNKNOWN),
                        "permit_type_raw": "large_load_service_contract",
                        "description": evidence.summary,
                        "status": row["status"],
                        "issuing_authority": "Michigan Public Service Commission",
                        "jurisdiction": row["location_name"],
                        "applied_date": None,
                        "issued_date": observed_at,
                        "address_raw": None,
                        "latitude": None,
                        "longitude": None,
                        "attributes": {
                            "docket_number": row["docket_number"],
                            "utility_name": row["utility_name"],
                            "customer_name": row["customer_name"],
                            "parent_company_name": row["parent_company_name"],
                            "project_type": row["project_type"],
                            "reported_load_mw": row["reported_load_mw"],
                            "location_name": row["location_name"],
                            "county_name": row["county_name"],
                            "state_code": row["state_code"],
                            "location_precision": row["location_precision"],
                        },
                    },
                    fields=fields,
                    evidence=[evidence],
                    geometry_wkt=None,
                    warnings=[
                        "Township-level source location; no point or parcel geometry emitted."
                    ],
                )
            ]
        )


__all__ = ["MPSC_U_21990_URL", "MpscLargeLoadConnector"]
