"""Connector for Copernicus Sentinel-2 Satellite Imagery (Mocked via Fixtures)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from helios_common.logging import get_logger
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
    NormalizationResult,
    NormalizedRecord,
    ParsedDocument,
    ParseResult,
    RawDocument,
    SourceItem,
)
from helios_remote_sensing import analyze_change
from helios_domain.ontology import StageEvidenceKind

logger = get_logger(__name__)

CONNECTOR_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"


class CopernicusSentinel2Connector(FixtureBackedConnector):
    """Parses Copernicus Sentinel-2 change detection records from local fixtures.
    
    Since we lack Copernicus credentials in this environment, this fixture-backed 
    connector simulates the change detection pipeline by reading mock JSON results.
    """

    fixture_dir = "copernicus_sentinel2"

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="copernicus-sentinel2",
            source_slug="copernicus-sentinel2",
            name="Copernicus Sentinel-2 Surface Reflectance",
            agency="European Space Agency / Copernicus",
            jurisdiction="Global",
            category=SourceCategory.REMOTE_SENSING,
            access_method=AccessMethod.REST_JSON,
            base_url="https://catalogue.dataspace.copernicus.eu/",
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.FIXTURE_ONLY,
            update_frequency="weekly",
            rate_limit_per_second=1.0,
            license_name="Copernicus open licence",
            license_url=None,
            robots_policy_status="allowed",
            geographic_coverage="Global",
            historical_coverage="2015 onward.",
            reliability_score=0.9,
            known_schema_issues="Fixture-backed only for now.",
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Discover change detection results from the fixture directory."""
        from pathlib import Path

        fixture_path = Path("fixtures") / self.fixture_dir
        items = []
        if fixture_path.exists():
            for json_file in fixture_path.glob("*.json"):
                items.append(
                    SourceItem(
                        source_native_id=f"sentinel2:{json_file.name}",
                        url=f"file://{json_file.absolute()}",
                        title=f"Sentinel-2 Change Record: {json_file.name}",
                        document_type="sentinel2_change_record",
                        hints={
                            "fixture_path": str(json_file),
                            "mime_type": "application/json",
                            "filename": json_file.name,
                        },
                    )
                )

        return DiscoveryResult(items=items)

    def parse(self, document: RawDocument) -> ParseResult:
        """Parse the JSON fixture into records."""
        try:
            payload_str = document.payload.decode("utf-8")
            data = json.loads(payload_str)
            if not isinstance(data, list):
                data = [data]
        except Exception as exc:
            return ParseResult(document=None, error=f"Failed to parse JSON: {exc}")

        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="sentinel2_change_record",
                records=data,
                field_signature=self.field_signature(data),
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Normalize extracted change detection records into evidence."""
        records: list[NormalizedRecord] = []
        rejected = 0
        filtered = 0

        for index, row in enumerate(document.records):
            parcel_id = row.get("parcel_id")
            observation_date_str = row.get("observation_date")
            
            ndsi_change = row.get("ndsi_change", 0.0)
            ndvi_change = row.get("ndvi_change", 0.0)
            cloud_cover = row.get("cloud_cover", 0.0)
            
            if not parcel_id or not observation_date_str:
                filtered += 1
                continue
                
            change_result = analyze_change(ndsi_change, ndvi_change, cloud_cover)
            
            # Only emit evidence if disturbance is confident
            if not change_result.is_significant:
                filtered += 1
                continue

            try:
                obs_date = date.fromisoformat(observation_date_str)
                records.append(
                    self._normalize_row(
                        parcel_id, 
                        change_result.confidence, 
                        change_result.description,
                        obs_date, 
                        index=index
                    )
                )
            except Exception as exc:
                logger.warning("copernicus.normalize_rejected", error=str(exc), index=index)
                rejected += 1

        return NormalizationResult(records=records, rejected=rejected, filtered=filtered)

    def _normalize_row(
        self, 
        parcel_id: str, 
        disturbance_score: float, 
        description: str,
        obs_date: date, 
        *, 
        index: int
    ) -> NormalizedRecord:
        """Create a NormalizedRecord from satellite metrics."""
        
        source_native_id = f"sentinel2-{parcel_id}-{obs_date.isoformat()}"
        
        evidence = [
            EvidenceItem(
                kind=str(StageEvidenceKind.SATELLITE_CONSTRUCTION_CHANGE),
                summary=description,
                observed_at=obs_date,
                confidence=disturbance_score,
                assertion_class=AssertionClass.PREDICTED,
                extraction_method=ExtractionMethod.STATISTICAL_MODEL,
                locator=f"$[{index}]",
                snippet=f"Parcel {parcel_id} NDSI/NDVI change threshold met",
                fields=[
                    ExtractedField(
                        name="disturbance_score",
                        value=str(disturbance_score),
                        confidence=1.0,
                        assertion_class=AssertionClass.CALCULATED,
                        extraction_method=ExtractionMethod.STATISTICAL_MODEL,
                        locator=f"$[{index}].disturbance_score",
                    )
                ],
            )
        ]

        return NormalizedRecord(
            entity_type="satellite_observation",
            source_native_id=source_native_id,
            payload={
                "source_native_id": source_native_id,
                "parcel_id": parcel_id,
                "disturbance_score": disturbance_score,
                "observation_date": obs_date.isoformat(),
            },
            fields=[],
            evidence=evidence,
        )


__all__ = ["CopernicusSentinel2Connector"]
