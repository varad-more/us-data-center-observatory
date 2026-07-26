"""Contract tests for the City of Mesa building-permits connector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import ConnectorStatus
from helios_connectors.mesa_permits import MesaBuildingPermitsConnector
from helios_connectors.types import DateRange, RawDocument, SourceItem
from helios_domain.ontology import StageEvidenceKind
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract

FIXTURE = ("mesa_permits", "east_valley_com.json")


@pytest.fixture
def connector() -> MesaBuildingPermitsConnector:
    return MesaBuildingPermitsConnector(street_filters=("SIGNAL BUTTE", "ELLSWORTH"))


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        item=SourceItem(
            source_native_id="mesa-permits:test",
            url="https://data.mesaaz.gov/resource/a2ui-hcuj.json",
            document_type="mesa_permits_json",
        ),
        payload=load_fixture_bytes(*FIXTURE),
        mime_type="application/json",
        retrieved_at=datetime(2026, 7, 26, tzinfo=UTC),
        http_status=200,
    )


class TestMetadata:
    def test_is_implemented(self, connector: MesaBuildingPermitsConnector) -> None:
        assert connector.get_metadata().status == ConnectorStatus.IMPLEMENTED

    def test_discovery_is_one_document(self, connector: MesaBuildingPermitsConnector) -> None:
        assert len(connector.discover(DateRange()).items) == 1


class TestNormalize:
    def test_emits_construction_permit_evidence(
        self, connector: MesaBuildingPermitsConnector, raw_document: RawDocument
    ) -> None:
        parsed = connector.parse(raw_document)
        assert parsed.ok and parsed.document is not None
        assert len(parsed.document.records) >= 3
        normalized = connector.normalize(parsed.document)
        assert normalized.records
        kinds = {item.kind for record in normalized.records for item in record.evidence}
        assert kinds == {str(StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT)}
        addresses = {record.payload["address_raw"] for record in normalized.records}
        assert "3740 S SIGNAL BUTTE RD" in addresses
