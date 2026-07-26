"""Contract tests for the EPA ECHO air facilities connector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import ConnectorStatus
from helios_connectors.epa_echo import EpaEchoAirConnector
from helios_connectors.types import DateRange, RawDocument, SourceItem
from helios_domain.ontology import StageEvidenceKind
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract

FIXTURE = ("epa_echo", "mesa_air_facilities.json")


@pytest.fixture
def connector() -> EpaEchoAirConnector:
    return EpaEchoAirConnector(cities=("Mesa", "Chandler"))


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        item=SourceItem(
            source_native_id="echo:air:test",
            url="https://echodata.epa.gov/echo/air_rest_services.get_facilities",
            document_type="echo_air_facilities_json",
        ),
        payload=load_fixture_bytes(*FIXTURE),
        mime_type="application/json",
        retrieved_at=datetime(2026, 7, 26, tzinfo=UTC),
        http_status=200,
    )


class TestMetadata:
    def test_is_implemented(self, connector: EpaEchoAirConnector) -> None:
        assert connector.get_metadata().status == ConnectorStatus.IMPLEMENTED

    def test_discovery_is_one_merged_document(self, connector: EpaEchoAirConnector) -> None:
        result = connector.discover(DateRange())
        assert len(result.items) == 1


class TestParseAndNormalize:
    def test_parses_facility_rows(
        self, connector: EpaEchoAirConnector, raw_document: RawDocument
    ) -> None:
        parsed = connector.parse(raw_document)
        assert parsed.ok and parsed.document is not None
        assert len(parsed.document.records) == 4

    def test_keeps_hosting_facilities_and_filters_others(
        self, connector: EpaEchoAirConnector, raw_document: RawDocument
    ) -> None:
        parsed = connector.parse(raw_document)
        assert parsed.document is not None
        normalized = connector.normalize(parsed.document)
        assert len(normalized.records) == 2
        assert normalized.filtered == 2
        names = {record.payload["attributes"]["facility_name"] for record in normalized.records}
        assert "PLATYPUS CAMPUS EMERGENCY GENERATORS" in names
        assert "DESERT READY MIX PLANT 7" not in names

    def test_emits_backup_generator_evidence(
        self, connector: EpaEchoAirConnector, raw_document: RawDocument
    ) -> None:
        parsed = connector.parse(raw_document)
        assert parsed.document is not None
        normalized = connector.normalize(parsed.document)
        kinds = {item.kind for record in normalized.records for item in record.evidence}
        assert kinds == {str(StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT)}
        assert all(
            item.is_standing_condition for record in normalized.records for item in record.evidence
        )
