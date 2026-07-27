"""Connector for Mesa Planning & Zoning Agendas.

This connector uses a FixtureBackedConnector to parse downloaded PDF agendas
for mentions of data centers, substations, and related keywords, extracting text snippets
using document intelligence.
"""

from __future__ import annotations

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
from helios_document_intelligence import extract_text_from_pdf, find_keywords_in_text
from helios_domain.ontology import StageEvidenceKind

logger = get_logger(__name__)

CONNECTOR_VERSION = "0.1.0"
PARSER_VERSION = "0.1.0"

KEYWORDS = ["data center", "data centre", "substation", "hyperscale", "server farm"]


class MesaAgendasConnector(FixtureBackedConnector):
    """Parses Mesa Planning & Zoning Agendas from local fixtures."""

    fixture_dir = "mesa_agendas"

    def get_metadata(self) -> ConnectorMetadata:
        """Return the connector description."""
        return ConnectorMetadata(
            slug="mesa-agendas",
            source_slug="mesa-agendas",
            name="City of Mesa Planning Agendas",
            agency="City of Mesa",
            jurisdiction="Mesa, Arizona",
            category=SourceCategory.MUNICIPAL_PLANNING,
            access_method=AccessMethod.MANUAL_UPLOAD,
            base_url="https://www.mesaaz.gov/government/advisory-boards-committees/planning-zoning-board",
            connector_version=CONNECTOR_VERSION,
            parser_version=PARSER_VERSION,
            status=ConnectorStatus.IMPLEMENTED,
            update_frequency="monthly",
            rate_limit_per_second=1.0,
            license_name="Public Domain",
            license_url=None,
            robots_policy_status="unknown",
            geographic_coverage="Mesa, Arizona",
            historical_coverage="Various",
            reliability_score=0.9,
            known_schema_issues="PDF extraction may have formatting artifacts.",
        )

    def discover(self, date_range: DateRange) -> DiscoveryResult:
        """Discover agenda PDFs from the fixture directory."""
        from pathlib import Path

        # Assuming fixtures are under `fixtures/mesa_agendas/`
        # In a real environment, this might look up a known index or manifest.
        # For this fixture-backed connector, we'll assume a specific manifest or
        # just yield a dummy item if we don't have a dynamic list, but since
        # discovery typically returns items from a known list, we'll construct
        # one based on expected fixtures or a metadata file.
        fixture_path = Path("fixtures") / self.fixture_dir
        items = []
        if fixture_path.exists():
            for pdf_file in fixture_path.glob("*.pdf"):
                items.append(
                    SourceItem(
                        source_native_id=f"mesa-agenda:{pdf_file.name}",
                        url=f"file://{pdf_file.absolute()}",
                        title=f"Mesa Planning Agenda: {pdf_file.name}",
                        document_type="mesa_agenda_pdf",
                        hints={
                            "fixture_path": str(pdf_file),
                            "mime_type": "application/pdf",
                            "filename": pdf_file.name,
                        },
                    )
                )

        return DiscoveryResult(items=items)

    def parse(self, document: RawDocument) -> ParseResult:
        """Extract text from the PDF payload."""
        try:
            text = extract_text_from_pdf(document.payload)
        except Exception as exc:
            return ParseResult(document=None, error=f"Failed to parse PDF: {exc}")

        return ParseResult(
            document=ParsedDocument(
                raw=document,
                document_type="mesa_agenda_pdf",
                records=[{"text": text, "filename": document.item.hints.get("filename")}],
                field_signature=self.field_signature([{"text": "dummy"}]),
            )
        )

    def normalize(self, document: ParsedDocument) -> NormalizationResult:
        """Normalize extracted text into evidence records."""
        records: list[NormalizedRecord] = []
        rejected = 0
        filtered = 0

        for index, row in enumerate(document.records):
            text = row.get("text", "")
            filename = row.get("filename", "unknown.pdf")

            snippets = find_keywords_in_text(text, KEYWORDS)

            if not snippets:
                filtered += 1
                continue

            try:
                records.append(self._normalize_row(filename, snippets, index=index))
            except Exception as exc:
                logger.warning("mesa_agendas.normalize_rejected", error=str(exc), index=index)
                rejected += 1

        return NormalizationResult(records=records, rejected=rejected, filtered=filtered)

    def _normalize_row(self, filename: str, snippets: list[str], *, index: int) -> NormalizedRecord:
        """Create a NormalizedRecord from keyword snippets."""
        from helios_common.time import utcnow

        source_native_id = f"agenda-{filename}"

        evidence = []
        for i, snippet in enumerate(snippets):
            evidence.append(
                EvidenceItem(
                    kind=str(StageEvidenceKind.PLANNING_APPLICATION_DATA_CENTER),
                    summary=f"Found data center related keyword in {filename}",
                    observed_at=utcnow().date(),  # Ideally extract date from text/filename
                    confidence=0.8,
                    assertion_class=AssertionClass.EXTRACTED,
                    extraction_method=ExtractionMethod.REGEX,
                    locator=f"snippet_{i}",
                    snippet=snippet,
                    fields=[
                        ExtractedField(
                            name="matched_text",
                            value=snippet,
                            confidence=0.9,
                            assertion_class=AssertionClass.EXTRACTED,
                            extraction_method=ExtractionMethod.REGEX,
                            locator=f"snippet_{i}",
                        )
                    ],
                )
            )

        return NormalizedRecord(
            entity_type="planning_agenda",
            source_native_id=source_native_id,
            payload={
                "source_native_id": source_native_id,
                "filename": filename,
                "snippets_found": len(snippets),
            },
            fields=[],
            evidence=evidence,
        )


__all__ = ["MesaAgendasConnector"]
