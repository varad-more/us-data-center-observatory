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


class _ScriptedHttp:
    """Returns a queued body per call, so paging can be exercised offline."""

    def __init__(self, bodies: list[bytes]) -> None:
        self.bodies = bodies
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, dict(params or {})))
        index = min(len(self.calls) - 1, len(self.bodies) - 1)
        return SimpleNamespace(content=self.bodies[index], status_code=200, elapsed_ms=1)


def _page(rows: list[dict[str, object]], **results: object) -> bytes:
    return json.dumps({"Results": {"Facilities": rows, **results}}).encode()


def _rows(start: int, count: int, state: str = "VA") -> list[dict[str, object]]:
    return [
        {
            "RegistryID": str(start + i),
            "SourceID": str(start + i),
            "AIRName": f"FACILITY {start + i}",
            "AIRNAICS": "518210",
            "AIRState": state,
            "AIRCity": "ASHBURN",
            "AIRStreet": "1 EXAMPLE WAY",
            "FacLat": "39.0",
            "FacLong": "-77.5",
            "FacFIPSCode": "51107",
        }
        for i in range(count)
    ]


class TestNationalPaging:
    """A national query returns far more than one page. It previously returned one row."""

    def test_asks_for_a_real_page_size(self) -> None:
        """``responseset`` is the page size. It was 1, so ECHO handed back a
        single facility for a query matching hundreds."""
        connector, http = _industry_connector()
        connector.fetch(connector.discover(DateRange()).items[0])
        assert int(http.calls[0][1]["responseset"]) > 1

    def test_pages_until_the_reported_row_count_is_reached(self) -> None:
        bodies = [
            _page([], QueryID="7", QueryRows="5"),
            _page(_rows(0, 3), QueryID="7"),
            _page(_rows(3, 2), QueryID="7"),
            _page([], QueryID="7"),
        ]
        http = _ScriptedHttp(bodies)
        connector = EpaEchoAirConnector(
            naics_codes=HOSTING_NAICS_QUERY,
            state=None,
            http_client=http,  # type: ignore[arg-type]
        )
        result = connector.fetch(connector.discover(DateRange()).items[0])
        assert result.document is not None
        payload = json.loads(result.document.payload)
        assert len(payload["Results"]["Facilities"]) == 5
        assert [call[1].get("pageno") for call in http.calls[1:]] == ["1", "2"]

    def test_reports_a_short_read_rather_than_hiding_it(self) -> None:
        """If ECHO promises rows it does not deliver, that is a coverage gap and
        has to reach the run summary."""
        bodies = [
            _page([], QueryID="7", QueryRows="9"),
            _page(_rows(0, 2), QueryID="7"),
            _page([], QueryID="7"),
        ]
        http = _ScriptedHttp(bodies)
        connector = EpaEchoAirConnector(
            naics_codes=HOSTING_NAICS_QUERY,
            state=None,
            http_client=http,  # type: ignore[arg-type]
        )
        result = connector.fetch(connector.discover(DateRange()).items[0])
        assert result.document is not None
        warnings = json.loads(result.document.payload)["_helios_query"]["warnings"]
        assert any("9" in w and "2" in w for w in warnings)

    def test_does_not_count_an_embedded_page_twice(self) -> None:
        embedded = _rows(0, 2)
        bodies = [
            _page(embedded, QueryID="7", QueryRows="4"),
            _page(embedded + _rows(2, 2), QueryID="7"),
            _page([], QueryID="7"),
        ]
        http = _ScriptedHttp(bodies)
        connector = EpaEchoAirConnector(
            naics_codes=HOSTING_NAICS_QUERY,
            state=None,
            http_client=http,  # type: ignore[arg-type]
        )
        result = connector.fetch(connector.discover(DateRange()).items[0])
        assert result.document is not None
        rows = json.loads(result.document.payload)["Results"]["Facilities"]
        assert len(rows) == 4
        assert len({row["RegistryID"] for row in rows}) == 4

    def test_duplicate_rows_are_not_reported_as_a_coverage_gap(self) -> None:
        """ECHO's own count includes repeated RegistryIDs - 447 reported and
        delivered, 440 distinct. Calling that a short read would invent a gap."""
        duplicated = _rows(0, 3) + _rows(2, 1)
        bodies = [
            _page([], QueryID="7", QueryRows="4"),
            _page(duplicated, QueryID="7"),
            _page([], QueryID="7"),
        ]
        http = _ScriptedHttp(bodies)
        connector = EpaEchoAirConnector(
            naics_codes=HOSTING_NAICS_QUERY,
            state=None,
            http_client=http,  # type: ignore[arg-type]
        )
        result = connector.fetch(connector.discover(DateRange()).items[0])
        assert result.document is not None
        payload = json.loads(result.document.payload)
        assert len(payload["Results"]["Facilities"]) == 3
        warnings = payload["_helios_query"]["warnings"]
        assert any("repeated a RegistryID" in w for w in warnings)
        assert not any("delivered" in w for w in warnings)


class TestNationalAttribution:
    """Outside Arizona, a row must describe the state it actually names."""

    def _normalize(self, rows: list[dict[str, object]]):
        connector = EpaEchoAirConnector(naics_codes=HOSTING_NAICS_QUERY, state=None)
        document = RawDocument(
            item=SourceItem(
                source_native_id="echo:air:naics:us:test",
                url="https://echodata.epa.gov/echo/air_rest_services.get_facilities",
                document_type="echo_air_facilities_json",
            ),
            payload=_page(rows),
            mime_type="application/json",
            retrieved_at=datetime(2026, 7, 28, tzinfo=UTC),
            http_status=200,
        )
        parsed = connector.parse(document)
        assert parsed.document is not None
        return connector.normalize(parsed.document)

    def test_keeps_rows_whose_naics_arrives_as_airnaics(self) -> None:
        """The national payload carries AIRNAICS and no Fac* columns. Reading
        only FacNAICSCodes discarded most of what the query asked for."""
        normalized = self._normalize(_rows(0, 3))
        assert len(normalized.records) == 3
        assert normalized.filtered == 0

    def test_address_carries_the_records_own_state(self) -> None:
        normalized = self._normalize(_rows(0, 1, state="VA"))
        address = normalized.records[0].payload["address_raw"]
        assert address.endswith("VA")
        assert "AZ" not in address

    def test_jurisdiction_is_never_defaulted_to_arizona(self) -> None:
        rows = _rows(0, 1, state="OH")
        rows[0]["AIRCity"] = ""
        normalized = self._normalize(rows)
        assert normalized.records[0].payload["jurisdiction"] == "OH"

    def test_state_and_county_fips_are_carried_for_grouping(self) -> None:
        normalized = self._normalize(_rows(0, 1, state="VA"))
        attributes = normalized.records[0].payload["attributes"]
        assert attributes["state"] == "VA"
        assert attributes["county_fips"] == "51107"
