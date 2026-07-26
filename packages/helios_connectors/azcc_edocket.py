"""Fixture-backed connector for Arizona Corporation Commission eDocket filings.

Live eDocket search is a stateful ASP.NET application without a documented API.
Automating it would require defeating session/viewstate controls, which Helios
refuses to do. Instead this connector:

* ships a parser/normalizer that understands a documented docket JSON schema;
* discovers recorded fixtures under ``tests/fixtures/azcc_edocket``;
* emits ``substation_application`` / ``transmission_filing`` evidence so the
  scoring model and UI can exercise the highest-weight early-warning path;
* keeps registry status at ``fixture_only`` with an explicit access limitation.

Fixtures are synthetic but schema-faithful. They must never be presented as a
live ACC scrape.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
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
from helios_connectors.base import FixtureBackedConnector
from helios_connectors.types import (
    ConnectorMetadata,
    DateRange,
    DiscoveryResult,
    EvidenceItem,
    ExtractedField,
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

EDOCKET_BASE_URL = "https://edocket.azcc.gov/"

_CATEGORY_TO_KIND: dict[str, StageEvidenceKind] = {
    "substation_application": StageEvidenceKind.SUBSTATION_APPLICATION,
    "transmission_filing": StageEvidenceKind.TRANSMISSION_FILING,
}


def default_fixture_dir() -> Path:
    """Return the repository fixture directory for ACC eDocket payloads."""
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "azcc_edocket"


class AzccEdocketConnector(FixtureBackedConnector):
    """Parses recorded ACC eDocket payloads; does not scrape the live UI."""

    fixture_dir = "azcc_edocket"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        fixture_root: Path | None = None,
    ) -> None:
        """Initialise the fixture-backed connector.

        Args:
            settings: Configuration override.
            fixture_root: Directory of ``*.json`` docket fixtures.
        """
        super().__init__(http_client=None, settings=settings)
        self._fixture_root = Path(fixture_root) if fixture_root else default_fixture_dir()

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="azcc-edocket",
            source_slug="azcc-edocket",
            name="Arizona Corporation Commission eDocket",
            agency="Arizona Corporation Commission",
            jurisdiction="Arizona",
            category=SourceCategory.UTILITY_AND_REGULATORY,
            access_method=AccessMethod.HTML_PAGE,
            base_url=EDOCKET_BASE_URL,
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.FIXTURE_ONLY,
            update_frequency="daily",
            geographic_coverage="Arizona",
            historical_coverage="Utility dockets with deep history (fixtures only here).",
            reliability_score=0.8,
            access_limitation=(
                "eDocket search is a stateful ASP.NET interface requiring viewstate "
                "round-trips and offering no documented API or bulk export. Helios "
                "implements and tests the parser against fixtures and does not automate "
                "the search interface."
            ),
            known_schema_issues=(
                "Fixture schema is Helios-normalized JSON derived from the public docket "
                "header/filing list, not a vendor export format."
            ),
        )

    def health_check(self) -> HealthCheckResult:
        """Fixture connectors are healthy when recorded payloads are present."""
        fixtures = list(self._fixture_root.glob("*.json"))
        return HealthCheckResult(
            healthy=bool(fixtures),
            checked_at=utcnow(),
            message=(
                f"{len(fixtures)} fixture docket(s) available"
                if fixtures
                else f"No fixtures under {self._fixture_root}"
            ),
            detail={"fixture_root": str(self._fixture_root), "count": len(fixtures)},
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Enumerate recorded docket fixtures as discoverable items."""
        del date_range  # fixtures are not date-windowed
        items: list[SourceItem] = []
        if not self._fixture_root.exists():
            warning = f"Missing fixture root {self._fixture_root}"
            return DiscoveryResult(items=[], warnings=[warning])

        for path in sorted(self._fixture_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                docket = payload["docket"]
                docket_number = str(docket["docket_number"])
            except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("azcc.fixture_unreadable", path=str(path), error=str(exc))
                continue
            items.append(
                SourceItem(
                    source_native_id=f"azcc-docket:{docket_number}",
                    url=str(docket.get("docket_url") or EDOCKET_BASE_URL),
                    title=f"ACC docket {docket_number}",
                    document_type="azcc_edocket_json",
                    published_date=_parse_date(docket.get("opened_date")),
                    hints={
                        "fixture_path": str(path),
                        "mime_type": "application/json",
                    },
                )
            )
        return DiscoveryResult(items=items)

    def parse(self, document: RawDocument) -> ParseResult:
        """Parse a fixture docket document into source-native records."""
        try:
            payload = json.loads(document.payload.decode("utf-8"))
            docket = payload["docket"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            return ParseResult(document=None, error=f"Invalid ACC fixture: {exc}")

        filings = list(docket.get("filings") or [])
        records = [{**filing, "_docket": docket} for filing in filings]
        if not records:
            # Treat the docket header itself as one filing-shaped record.
            records = [
                {
                    "filing_id": f"{docket['docket_number']}-header",
                    "filed_date": docket.get("opened_date"),
                    "filing_type": docket.get("docket_type"),
                    "title": docket.get("description"),
                    "description": docket.get("description"),
                    "category": "substation_application",
                    "_docket": docket,
                }
            ]

        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="azcc_edocket_json",
                records=records,
                field_signature=self.field_signature(records),
                warnings=[
                    "Fixture-backed payload; not retrieved from live eDocket search.",
                ],
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Map filings onto permit entities with stage evidence."""
        records: list[NormalizedRecord] = []
        rejected = 0
        for index, row in enumerate(document.records):
            try:
                normalized = self._normalize_filing(row, index=index)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("azcc.normalize_rejected", error=str(exc), index=index)
                rejected += 1
                continue
            if normalized is None:
                rejected += 1
                continue
            records.append(normalized)
        return NormalizationResult(
            records=records,
            rejected=rejected,
            warnings=list(document.warnings),
        )

    def _normalize_filing(self, row: dict[str, Any], *, index: int) -> NormalizedRecord | None:
        """Normalize one filing row."""
        docket = row["_docket"]
        category = str(row.get("category") or "").strip().lower()
        kind = _CATEGORY_TO_KIND.get(category)
        if kind is None:
            return None

        filing_id = str(row["filing_id"])
        filed = _parse_date(row.get("filed_date")) or _parse_date(docket.get("opened_date"))
        if filed is None:
            raise ValueError(f"Filing {filing_id} has no filed_date")

        lat = docket.get("latitude")
        lon = docket.get("longitude")
        geometry = None
        if lat is not None and lon is not None:
            geometry = f"POINT({float(lon)} {float(lat)})"

        utility = str(docket.get("utility_name") or "Unknown utility")
        title = str(row.get("title") or row.get("filing_type") or kind.value)
        summary = (
            f"ACC docket {docket['docket_number']}: {title}. Filed by {utility} on "
            f"{filed.isoformat()}. Helios ingested a recorded fixture, not a live scrape."
        )

        fields = [
            ExtractedField(
                name="docket_number",
                value=docket["docket_number"],
                confidence=1.0,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator="$.docket.docket_number",
            ),
            ExtractedField(
                name="utility_name",
                value=utility,
                confidence=0.95,
                assertion_class=AssertionClass.REPORTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator="$.docket.utility_name",
            ),
            ExtractedField(
                name="filing_category",
                value=category,
                confidence=0.9,
                assertion_class=AssertionClass.EXTRACTED,
                extraction_method=ExtractionMethod.PATTERN_RULE,
                locator=f"$.docket.filings[{index}].category",
            ),
        ]

        evidence = [
            EvidenceItem(
                kind=str(kind),
                summary=summary,
                observed_at=filed,
                confidence=0.85,
                assertion_class=AssertionClass.EXTRACTED,
                extraction_method=ExtractionMethod.STRUCTURED_FEED,
                locator=f"$.docket.filings[{index}]",
                snippet=str(row.get("description") or title),
                fields=fields,
            )
        ]

        return NormalizedRecord(
            entity_type="permit",
            source_native_id=filing_id,
            payload={
                "source_native_id": filing_id,
                "permit_number": docket["docket_number"],
                "category": str(PermitCategory.UNKNOWN),
                "permit_type_raw": str(row.get("filing_type") or category),
                "description": str(row.get("description") or title),
                "status": docket.get("status"),
                "issuing_authority": "Arizona Corporation Commission",
                "jurisdiction": docket.get("nearest_city") or docket.get("county") or "Arizona",
                "applied_date": filed,
                "issued_date": None,
                "address_raw": None,
                "latitude": float(lat) if lat is not None else None,
                "longitude": float(lon) if lon is not None else None,
                "attributes": {
                    "docket_number": docket["docket_number"],
                    "utility_name": utility,
                    "filing_category": category,
                    "fixture_backed": True,
                },
            },
            fields=fields,
            evidence=evidence,
            geometry_wkt=geometry,
            warnings=["fixture_backed"],
        )


def _parse_date(value: object) -> date | None:
    """Parse an ISO calendar date."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


__all__ = ["AzccEdocketConnector", "default_fixture_dir"]
