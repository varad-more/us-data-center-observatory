"""Contract tests for the EPA ECHO air facilities connector."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from helios_common.vocabulary import ConnectorStatus
from helios_connectors.epa_echo import HOSTING_NAICS_QUERY, EpaEchoAirConnector
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


class _RecordingHttp:
    """Captures outgoing query parameters without touching the network."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, dict(params or {})))
        return SimpleNamespace(content=self.body, status_code=200, elapsed_ms=1)


def _industry_connector(rows: int = 1) -> tuple[EpaEchoAirConnector, _RecordingHttp]:
    body = json.dumps(
        {"Results": {"QueryID": "1", "Facilities": [{"RegistryID": str(i)} for i in range(rows)]}}
    ).encode()
    http = _RecordingHttp(body)
    connector = EpaEchoAirConnector(
        naics_codes=HOSTING_NAICS_QUERY, state=None, http_client=http  # type: ignore[arg-type]
    )
    return connector, http


class TestIndustryMode:
    """City enumeration cannot cover a country; NAICS filtering can."""

    def test_uses_p_ncs_not_p_naics(self) -> None:
        """ECHO accepts p_naics and silently ignores it, returning every row in
        scope. Sending the wrong name would look like a working national query
        that had in fact filtered nothing."""
        connector, http = _industry_connector()
        connector.fetch(connector.discover(DateRange()).items[0])
        _, params = http.calls[0]
        assert params["p_ncs"] == "518210,541513"
        assert "p_naics" not in params

    def test_omits_state_when_nationwide(self) -> None:
        connector, http = _industry_connector()
        connector.fetch(connector.discover(DateRange()).items[0])
        assert "p_st" not in http.calls[0][1]

    def test_one_request_covers_the_country(self) -> None:
        """The point of the mode: six cities were six round trips against an API
        that throttles at roughly 300 an hour."""
        connector, http = _industry_connector()
        connector.fetch(connector.discover(DateRange()).items[0])
        assert len(http.calls) == 1

    def test_state_still_narrows_when_given(self) -> None:
        connector, http = _industry_connector()
        connector.state = "VA"
        connector.fetch(connector.discover(DateRange()).items[0])
        assert http.calls[0][1]["p_st"] == "VA"

    def test_city_mode_remains_the_default(self) -> None:
        """The study region and its recorded fixture are unaffected."""
        connector = EpaEchoAirConnector(cities=("Mesa", "Chandler"))
        assert not connector.is_industry_mode
        item = connector.discover(DateRange()).items[0]
        assert item.hints["cities"] == ["Mesa", "Chandler"]

    def test_city_mode_issues_one_request_per_city(self) -> None:
        connector, http = _industry_connector()
        connector.naics_codes = ()
        connector.cities = ("Mesa", "Chandler", "Tempe")
        connector.state = "AZ"
        connector.fetch(connector.discover(DateRange()).items[0])
        assert len(http.calls) == 3
        assert [call[1]["p_city"] for call in http.calls] == ["Mesa", "Chandler", "Tempe"]
