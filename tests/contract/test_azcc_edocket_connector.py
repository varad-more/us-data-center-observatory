"""Contract tests for the fixture-backed ACC eDocket connector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import ConnectorStatus
from helios_connectors.azcc_edocket import AzccEdocketConnector, default_fixture_dir
from helios_connectors.types import DateRange, RawDocument, SourceItem
from helios_domain.ontology import StageEvidenceKind
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract


@pytest.fixture
def connector() -> AzccEdocketConnector:
    return AzccEdocketConnector(fixture_root=default_fixture_dir())


class TestMetadata:
    def test_status_is_fixture_only(self, connector: AzccEdocketConnector) -> None:
        assert connector.get_metadata().status == ConnectorStatus.FIXTURE_ONLY
        assert connector.get_metadata().access_limitation


class TestDiscoverAndFetch:
    def test_discovers_recorded_dockets(self, connector: AzccEdocketConnector) -> None:
        result = connector.discover(DateRange())
        assert len(result.items) >= 2
        assert all("fixture_path" in item.hints for item in result.items)

    def test_fetch_reads_fixture_bytes(self, connector: AzccEdocketConnector) -> None:
        item = connector.discover(DateRange()).items[0]
        fetched = connector.fetch(item)
        assert fetched.ok
        assert fetched.document is not None
        assert fetched.document.headers.get("x-helios-fixture") == "true"


class TestNormalize:
    def test_emits_substation_application_evidence(self, connector: AzccEdocketConnector) -> None:
        raw = RawDocument(
            item=SourceItem(
                source_native_id="azcc-docket:E-01345A-22-0148",
                url="https://edocket.azcc.gov/",
                document_type="azcc_edocket_json",
            ),
            payload=load_fixture_bytes("azcc_edocket", "e-01345-substation.json"),
            mime_type="application/json",
            retrieved_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
        parsed = connector.parse(raw)
        assert parsed.ok and parsed.document is not None
        normalized = connector.normalize(parsed.document)
        assert normalized.error is None
        assert normalized.records
        kinds = {item.kind for record in normalized.records for item in record.evidence}
        assert str(StageEvidenceKind.SUBSTATION_APPLICATION) in kinds
        assert all(record.entity_type == "permit" for record in normalized.records)

    def test_emits_transmission_filing_evidence(self, connector: AzccEdocketConnector) -> None:
        raw = RawDocument(
            item=SourceItem(
                source_native_id="azcc-docket:E-01933A-21-0099",
                url="https://edocket.azcc.gov/",
                document_type="azcc_edocket_json",
            ),
            payload=load_fixture_bytes("azcc_edocket", "e-01933-transmission.json"),
            mime_type="application/json",
            retrieved_at=datetime(2026, 7, 26, tzinfo=UTC),
        )
        parsed = connector.parse(raw)
        assert parsed.ok and parsed.document is not None
        normalized = connector.normalize(parsed.document)
        kinds = {item.kind for record in normalized.records for item in record.evidence}
        assert str(StageEvidenceKind.TRANSMISSION_FILING) in kinds
