"""Connector for the Maricopa County Assessor parcel layer.

This is Helios's spatial and ownership backbone. It supplies parcel geometry,
the current recorded owner, the most recent deed with a link to the recorder's
copy, and - unusually valuable - the assessor's own ``DATA CENTERS`` property-use
classification, which doubles as reproducible ground truth for validation.

Provenance model
----------------
The service is a paged query API, not a document repository, so the *fetched
artifact* is one page of query results. Each page becomes a
:class:`SourceDocument` with a deterministic identifier derived from the query
signature, so re-running the same query maps onto the same document and produces
a new version only when the content genuinely changes. Individual parcels are
then cited by JSON path within that page (``$.features[7]``), which is what lets
the UI show exactly which bytes a fact came from.

Privacy
-------
The layer contains the names and mailing addresses of private homeowners. Every
owner name passes through the natural-person classifier during normalization and
is suppressed before persistence when the policy applies. Redactions are counted
and reported rather than performed silently.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from helios_common.config import Settings
from helios_common.hashing import short_hash
from helios_common.logging import get_logger
from helios_common.time import from_epoch_millis, utcnow
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
from helios_document_intelligence.units import acres_from_sqft
from helios_domain.ontology import StageEvidenceKind
from helios_entity_resolution.names import analyze_owner_name, apply_pii_policy

logger = get_logger(__name__)

CONNECTOR_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"

SERVICE_URL = "https://gis.maricopa.gov/arcgis/rest/services/RED/Assessor/MapServer"
PARCEL_LAYER = 1
MAX_RECORDS_PER_PAGE = 2000
"""The service's own ``maxRecordCount``; requesting more silently truncates."""

OUT_FIELDS: tuple[str, ...] = (
    "OBJECTID",
    "APN",
    "APNDash",
    "PropertyFullStreetAddress",
    "PropertyCity",
    "PropertyZipCode",
    "OwnerName",
    "OwnerCity",
    "OwnerState",
    "PropertyUseCode",
    "PropertyUseDescription",
    "LandLegalClassCode",
    "LotSize_Acre",
    "LotSize_SqFt",
    "ConstructionYear",
    "DeedNumber",
    "DeedDate",
    "DeedWebLink",
    "SaleDate",
    "SalePrice",
    "AssessorWebLink",
    "Longitude_DD",
    "Latitude_DD",
    "Township",
    "Range",
    "Section",
)
"""Deliberately narrow. Owner mailing street address is *not* requested, so
personal address data is never transmitted to Helios in the first place."""

DATA_CENTER_USE_DESCRIPTION = "DATA CENTERS"

LARGE_PARCEL_ACRE_THRESHOLD = 20.0
"""Above this, a single acquisition is notable for industrial development.
Chosen because the smallest assessor-classified data-center parcel in the county
sits near 1 acre while campus-scale holdings run 15-190 acres; 20 acres selects
campus-scale land without flooding the system with ordinary industrial lots."""

_INDUSTRIAL_USE_HINTS: tuple[str, ...] = (
    "DATA CENTER",
    "WAREHOUSE",
    "INDUSTRIAL",
    "MANUFACTURING",
    "VACANT COMMERCIAL",
    "VACANT INDUSTRIAL",
    "OFFICE BUILDING",
    "PART COMP",
)


class MaricopaAssessorConnector(BaseConnector):
    """Reads parcels from the Maricopa County ArcGIS assessor service."""

    def __init__(
        self,
        *,
        http_client: PoliteHttpClient | None = None,
        settings: Settings | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        where: str | None = None,
        page_size: int = 500,
    ) -> None:
        """Initialise the connector.

        Args:
            http_client: Shared HTTP client.
            settings: Configuration override.
            bbox: ``(min_lon, min_lat, max_lon, max_lat)`` spatial filter. Defaults
                to the configured study region.
            where: SQL-style attribute filter. Defaults to ``1=1``.
            page_size: Records per request, capped at the service maximum.
        """
        super().__init__(http_client=http_client, settings=settings)
        self.bbox = bbox
        self.where = where or "1=1"
        self.page_size = min(page_size, MAX_RECORDS_PER_PAGE)

    # ---------------------------------------------------------- metadata --

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="maricopa-assessor-parcels",
            source_slug="maricopa-assessor-parcels",
            name="Maricopa County Assessor Parcel Layer",
            agency="Maricopa County Assessor / Maricopa County GIS",
            jurisdiction="Maricopa County, Arizona",
            category=SourceCategory.LAND_AND_PROPERTY,
            access_method=AccessMethod.ARCGIS_REST,
            base_url=SERVICE_URL,
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.IMPLEMENTED,
            update_frequency="daily",
            rate_limit_per_second=2.0,
            license_name="Maricopa County open GIS data",
            attribution_required=True,
            attribution_text=(
                "Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS."
            ),
            robots_policy_status="not_applicable",
            contains_personal_data=True,
            geographic_coverage="Maricopa County, Arizona",
            historical_coverage=(
                "Current assessment roll. Only the most recent deed per parcel is exposed."
            ),
            reliability_score=0.95,
            known_schema_issues=(
                "Dates are epoch milliseconds; OwnerName mixes companies and individuals."
            ),
        )

    def health_check(self) -> HealthCheckResult:
        """Probe the layer metadata endpoint."""
        started = utcnow()
        try:
            response = self.http.get(f"{SERVICE_URL}/{PARCEL_LAYER}", params={"f": "json"})
            payload = json.loads(response.content)
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, checked_at=started, message=f"{type(exc).__name__}: {exc}"
            )

        if "error" in payload:
            return HealthCheckResult(
                healthy=False,
                checked_at=started,
                http_status=response.status_code,
                message=str(payload["error"]),
            )
        return HealthCheckResult(
            healthy=True,
            checked_at=started,
            latency_ms=response.elapsed_ms,
            http_status=response.status_code,
            detail={
                "layer_name": payload.get("name"),
                "max_record_count": payload.get("maxRecordCount"),
            },
        )

    # --------------------------------------------------------- discovery --

    def _query_params(self, offset: int) -> dict[str, Any]:
        """Build the ArcGIS query parameters for one page."""
        params: dict[str, Any] = {
            "where": self.where,
            "outFields": ",".join(OUT_FIELDS),
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": self.page_size,
            "orderByFields": "OBJECTID ASC",
        }
        if self.bbox:
            min_lon, min_lat, max_lon, max_lat = self.bbox
            params["geometry"] = f"{min_lon},{min_lat},{max_lon},{max_lat}"
            params["geometryType"] = "esriGeometryEnvelope"
            params["inSR"] = "4326"
            params["spatialRel"] = "esriSpatialRelIntersects"
        return params

    def _query_signature(self) -> str:
        """Stable identifier for the current query, used in document identity."""
        return short_hash(json.dumps({"where": self.where, "bbox": self.bbox}, sort_keys=True))

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Enumerate result pages for the configured query.

        ArcGIS reports whether more records remain via ``exceededTransferLimit``,
        so pages are discovered by walking offsets until the flag clears. The
        date range is not used as a server-side filter because the layer carries
        no reliable record-modified timestamp; filtering happens during
        normalization instead.

        Args:
            date_range: Window used downstream for evidence filtering.

        Returns:
            One :class:`SourceItem` per page.
        """
        items: list[SourceItem] = []
        errors: list[str] = []
        offset = 0
        signature = self._query_signature()

        # A hard page ceiling prevents an unexpected upstream change (or an
        # over-broad `where`) from turning discovery into an unbounded crawl.
        max_pages = 40
        for page in range(max_pages):
            params = self._query_params(offset)
            try:
                response = self.http.get(f"{SERVICE_URL}/{PARCEL_LAYER}/query", params=params)
                payload = json.loads(response.content)
            except Exception as exc:
                errors.append(f"page {page} at offset {offset}: {type(exc).__name__}: {exc}")
                break

            if "error" in payload:
                errors.append(f"page {page}: service error {payload['error']}")
                break

            features = payload.get("features", [])
            if not features:
                break

            items.append(
                SourceItem(
                    source_native_id=f"parcel-query:{signature}:offset:{offset}",
                    url=f"{SERVICE_URL}/{PARCEL_LAYER}/query",
                    title=f"Maricopa parcel query page {page + 1} (offset {offset})",
                    document_type="arcgis_query_page",
                    hints={"params": params, "offset": offset, "page": page},
                )
            )

            if not payload.get("exceededTransferLimit"):
                break
            offset += self.page_size
        else:
            errors.append(f"Stopped after {max_pages} pages; query may be too broad")

        logger.info(
            "maricopa_assessor.discovered",
            pages=len(items),
            where=self.where,
            bbox=self.bbox,
            errors=len(errors),
        )
        return DiscoveryResult(
            items=items,
            truncated=bool(errors),
            errors=errors,
            detail={"date_range": {"start": str(date_range.start), "end": str(date_range.end)}},
        )

    # ------------------------------------------------------------- fetch --

    def fetch(self, item: SourceItem) -> FetchResult:
        """Retrieve one page of parcel records."""
        params = item.hints.get("params") or self._query_params(item.hints.get("offset", 0))
        try:
            response = self.http.get(item.url, params=params)
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

    # ------------------------------------------------------------- parse --

    def parse(self, document: RawDocument) -> ParseResult:
        """Decode an ArcGIS query response into feature records."""
        try:
            payload = json.loads(document.payload)
        except json.JSONDecodeError as exc:
            return ParseResult(document=None, error=f"Invalid JSON: {exc}")

        if "error" in payload:
            return ParseResult(document=None, error=f"Service error: {payload['error']}")

        features = payload.get("features", [])
        records: list[dict[str, Any]] = []
        warnings: list[str] = []

        for index, feature in enumerate(features):
            attributes = dict(feature.get("attributes") or {})
            if not attributes.get("APN"):
                warnings.append(f"$.features[{index}] has no APN and was skipped")
                continue
            attributes["_geometry"] = feature.get("geometry")
            attributes["_locator"] = f"$.features[{index}]"
            records.append(attributes)

        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="arcgis_query_page",
                records=records,
                field_signature=self.field_signature(
                    [{k: v for k, v in r.items() if not k.startswith("_")} for r in records]
                ),
                warnings=warnings,
            )
        )

    # --------------------------------------------------------- normalize --

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Map assessor features onto Helios parcel records.

        Applies the PII policy, converts epoch-millisecond dates, derives acreage
        when the assessor omits it, and assigns an evidence kind describing what
        - if anything - makes each parcel interesting.

        Args:
            document: Parsed page of assessor features.

        Returns:
            One normalized record per parcel.
        """
        redaction_enabled = (self._settings or self.http.settings).redact_natural_person_names
        records: list[NormalizedRecord] = []
        rejected = 0
        warnings: list[str] = list(document.warnings)

        for attributes in document.records:
            try:
                record = self._normalize_one(attributes, redaction_enabled=redaction_enabled)
            except (ValueError, TypeError, KeyError) as exc:
                rejected += 1
                warnings.append(f"{attributes.get('_locator', '?')}: {type(exc).__name__}: {exc}")
                continue
            records.append(record)

        redacted_total = sum(1 for r in records if r.redactions_applied)
        if redacted_total:
            logger.info(
                "maricopa_assessor.pii_redacted",
                redacted_records=redacted_total,
                total_records=len(records),
            )

        return NormalizationResult(records=records, rejected=rejected, warnings=warnings)

    def _normalize_one(
        self, attributes: dict[str, Any], *, redaction_enabled: bool
    ) -> NormalizedRecord:
        """Normalize a single assessor feature."""
        apn_raw = str(attributes["APN"]).strip()
        apn = normalize_apn(apn_raw)
        locator = attributes.get("_locator", "$.features[?]")

        owner_analysis = analyze_owner_name(attributes.get("OwnerName"))
        storable_owner, was_redacted = apply_pii_policy(
            owner_analysis, redaction_enabled=redaction_enabled
        )

        deed_date = from_epoch_millis(attributes.get("DeedDate"))
        sale_date = from_epoch_millis(attributes.get("SaleDate"))

        acres = attributes.get("LotSize_Acre")
        sqft = attributes.get("LotSize_SqFt")
        acres_assertion = AssertionClass.REPORTED
        if acres is None and sqft:
            acres = acres_from_sqft(float(sqft))
            acres_assertion = AssertionClass.CALCULATED

        use_description = (attributes.get("PropertyUseDescription") or "").strip().upper()
        evidence_kind, evidence_summary = self._classify_evidence(
            use_description=use_description,
            acres=float(acres) if acres else None,
            owner_is_organization=not owner_analysis.classification.is_personal,
            deed_date=deed_date.date() if deed_date else None,
        )

        fields = self._build_fields(
            attributes=attributes,
            locator=locator,
            acres=acres,
            acres_assertion=acres_assertion,
            owner_stored=storable_owner,
            owner_redacted=was_redacted,
        )

        observed_source = deed_date or sale_date
        observed = observed_source.date() if observed_source is not None else None

        payload: dict[str, Any] = {
            "apn": apn,
            "apn_formatted": attributes.get("APNDash"),
            "county": "Maricopa",
            "situs_address": attributes.get("PropertyFullStreetAddress"),
            "situs_city": (attributes.get("PropertyCity") or "").title() or None,
            "situs_postal_code": attributes.get("PropertyZipCode"),
            "jurisdiction": (attributes.get("PropertyCity") or "").title() or None,
            "owner_name_raw": storable_owner,
            "owner_is_redacted": was_redacted,
            "owner_analysis": {
                "classification": str(owner_analysis.classification),
                "confidence": owner_analysis.confidence,
                "legal_form": owner_analysis.legal_form,
                "normalized_name": owner_analysis.normalized_name if not was_redacted else None,
                "is_suspected_shell": owner_analysis.is_suspected_shell,
                "shell_indicators": list(owner_analysis.shell_indicators),
                "mentions_data_center": owner_analysis.mentions_data_center,
                "reasons": list(owner_analysis.reasons),
            },
            "land_use_code": attributes.get("PropertyUseCode"),
            "land_use_description": attributes.get("PropertyUseDescription"),
            "legal_class_code": attributes.get("LandLegalClassCode"),
            "lot_size_acres": float(acres) if acres is not None else None,
            "lot_size_sqft": float(sqft) if sqft is not None else None,
            "construction_year": attributes.get("ConstructionYear"),
            "last_deed_number": attributes.get("DeedNumber"),
            "last_deed_date": deed_date.date() if deed_date else None,
            "last_deed_url": attributes.get("DeedWebLink"),
            "last_sale_date": sale_date.date() if sale_date else None,
            "last_sale_price": attributes.get("SalePrice"),
            "assessor_url": attributes.get("AssessorWebLink"),
            "longitude": attributes.get("Longitude_DD"),
            "latitude": attributes.get("Latitude_DD"),
            "locator": locator,
        }

        return NormalizedRecord(
            entity_type="parcel",
            source_native_id=apn,
            payload=payload,
            fields=fields,
            evidence_kind=evidence_kind,
            evidence_summary=evidence_summary,
            observed_at=observed,
            geometry_wkt=_esri_polygon_to_wkt(attributes.get("_geometry")),
            redactions_applied=["owner_name"] if was_redacted else [],
        )

    def _classify_evidence(
        self,
        *,
        use_description: str,
        acres: float | None,
        owner_is_organization: bool,
        deed_date: date | None,
    ) -> tuple[str | None, str | None]:
        """Decide what, if anything, makes this parcel evidentially interesting.

        Returns ``(None, None)`` for ordinary parcels so that the overwhelming
        majority of the county generates no evidence records at all.
        """
        if DATA_CENTER_USE_DESCRIPTION in use_description:
            return (
                str(StageEvidenceKind.ASSESSOR_DATA_CENTER_CLASSIFICATION),
                "County assessor classifies this parcel's property use as DATA CENTERS.",
            )

        is_industrial = any(hint in use_description for hint in _INDUSTRIAL_USE_HINTS)
        if (
            acres is not None
            and acres >= LARGE_PARCEL_ACRE_THRESHOLD
            and is_industrial
            and owner_is_organization
        ):
            when = f" recorded {deed_date.isoformat()}" if deed_date else ""
            return (
                str(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION),
                (
                    f"Organization-held industrial parcel of {acres:.1f} acres"
                    f"{when}, at or above the {LARGE_PARCEL_ACRE_THRESHOLD:.0f}-acre "
                    "campus-scale threshold."
                ),
            )
        return None, None

    def _build_fields(
        self,
        *,
        attributes: dict[str, Any],
        locator: str,
        acres: float | None,
        acres_assertion: AssertionClass,
        owner_stored: str | None,
        owner_redacted: bool,
    ) -> list[ExtractedField]:
        """Build the per-field provenance list for one parcel."""
        fields: list[ExtractedField] = []

        if acres is not None:
            fields.append(
                ExtractedField(
                    name="lot_size_acres",
                    value=round(float(acres), 4),
                    raw_text=str(attributes.get("LotSize_Acre") or attributes.get("LotSize_SqFt")),
                    raw_unit="acres" if attributes.get("LotSize_Acre") else "sqft",
                    normalized_unit="acres",
                    assertion_class=acres_assertion,
                    extraction_method=(
                        ExtractionMethod.STRUCTURED_FEED
                        if acres_assertion is AssertionClass.REPORTED
                        else ExtractionMethod.GEOMETRY_OPERATION
                    ),
                    confidence=0.95,
                    locator=f"{locator}.attributes.LotSize_Acre",
                )
            )

        if use_desc := attributes.get("PropertyUseDescription"):
            fields.append(
                ExtractedField(
                    name="land_use_description",
                    value=use_desc,
                    raw_text=use_desc,
                    assertion_class=AssertionClass.REPORTED,
                    extraction_method=ExtractionMethod.STRUCTURED_FEED,
                    confidence=0.95,
                    locator=f"{locator}.attributes.PropertyUseDescription",
                )
            )

        if owner_stored is not None:
            fields.append(
                ExtractedField(
                    name="owner_name",
                    value=owner_stored,
                    raw_text=owner_stored,
                    assertion_class=AssertionClass.REPORTED,
                    extraction_method=ExtractionMethod.STRUCTURED_FEED,
                    confidence=0.95,
                    locator=f"{locator}.attributes.OwnerName",
                )
            )
        elif owner_redacted:
            fields.append(
                ExtractedField(
                    name="owner_name",
                    value=None,
                    raw_text=None,
                    assertion_class=AssertionClass.UNKNOWN,
                    extraction_method=ExtractionMethod.RULE_ENGINE,
                    confidence=1.0,
                    locator=f"{locator}.attributes.OwnerName",
                    snippet="Owner name withheld: classified as a private individual.",
                )
            )

        if deed_number := attributes.get("DeedNumber"):
            fields.append(
                ExtractedField(
                    name="deed_number",
                    value=deed_number,
                    raw_text=str(deed_number),
                    assertion_class=AssertionClass.REPORTED,
                    extraction_method=ExtractionMethod.STRUCTURED_FEED,
                    confidence=0.98,
                    locator=f"{locator}.attributes.DeedNumber",
                )
            )

        return fields


def normalize_apn(raw: str) -> str:
    """Normalise an assessor parcel number for joining across sources.

    Maricopa APNs are not purely numeric: split and re-split parcels carry alpha
    suffixes such as ``304-33-005S``. Stripping non-digits would silently merge
    ``30433005S`` with ``30433005``, which are different parcels, so only
    formatting characters are removed.

    Args:
        raw: APN as printed by a source, with or without dashes.

    Returns:
        Upper-cased alphanumeric APN.
    """
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def _esri_polygon_to_wkt(geometry: dict[str, Any] | None) -> str | None:
    """Convert an Esri polygon to MultiPolygon WKT.

    Esri encodes polygons as a flat list of rings using winding order to
    distinguish outer boundaries from holes, which does not map onto WKT
    directly. Helios takes the conservative route of treating every ring as its
    own polygon: parcel geometry with true interior holes is rare, and inflating
    a parcel's apparent area is a safer error than dropping rings entirely.

    Args:
        geometry: Esri geometry dictionary, or ``None``.

    Returns:
        A ``MULTIPOLYGON`` WKT string, or ``None`` when there is no usable geometry.
    """
    if not geometry:
        return None
    rings = geometry.get("rings")
    if not rings:
        return None

    polygons: list[str] = []
    for ring in rings:
        if len(ring) < 4:
            continue  # A closed ring needs at least four coordinate pairs.
        coordinates = ring[:]
        if coordinates[0] != coordinates[-1]:
            coordinates.append(coordinates[0])
        points = ", ".join(f"{float(x)} {float(y)}" for x, y in coordinates)
        polygons.append(f"(({points}))")

    if not polygons:
        return None
    return f"MULTIPOLYGON({', '.join(polygons)})"


__all__ = [
    "DATA_CENTER_USE_DESCRIPTION",
    "LARGE_PARCEL_ACRE_THRESHOLD",
    "MaricopaAssessorConnector",
    "normalize_apn",
]
