"""Contract tests for the OpenStreetMap power-infrastructure connector.

Exercised against an Overpass response captured on 2026-07-25 for the East
Valley bounding box, filtered to substations and circuits at or above 115 kV.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import AssertionClass
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.types import RawDocument, SourceItem
from helios_document_intelligence.units import parse_voltage_list
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract

FIXTURE = ("osm_power", "east_valley_power.json")


@pytest.fixture
def connector() -> OsmPowerConnector:
    return OsmPowerConnector(bbox=(-111.98, 33.16, -111.35, 33.52))


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        item=SourceItem(
            source_native_id="overpass:power:test",
            url="https://overpass-api.de/api/interpreter",
            document_type="overpass_json",
        ),
        payload=load_fixture_bytes(*FIXTURE),
        mime_type="application/json",
        retrieved_at=datetime(2026, 7, 25, 21, 30, tzinfo=UTC),
        http_status=200,
    )


class TestVoltageParsing:
    def test_parses_semicolon_delimited_volts_to_kv(self) -> None:
        """OSM stores volts; Helios stores kV. Greenbone is a real multi-voltage site."""
        assert parse_voltage_list("500000;230000;69000") == [500.0, 230.0, 69.0]

    def test_returns_highest_first(self) -> None:
        assert parse_voltage_list("69000;230000")[0] == 230.0

    def test_handles_missing_and_junk_values(self) -> None:
        assert parse_voltage_list(None) == []
        assert parse_voltage_list("") == []
        assert parse_voltage_list("unknown") == []

    def test_passes_through_values_already_in_kv(self) -> None:
        assert parse_voltage_list("230") == [230.0]


class TestMetadata:
    def test_carries_odbl_attribution(self, connector: OsmPowerConnector) -> None:
        """ODbL obliges Helios to attribute; exports depend on this string existing."""
        metadata = connector.get_metadata()
        assert metadata.attribution_required is True
        assert "OpenStreetMap contributors" in (metadata.attribution_text or "")
        assert metadata.license_name is not None
        assert "ODbL" in metadata.license_name

    def test_documents_that_absence_is_not_evidence(self, connector: OsmPowerConnector) -> None:
        issues = connector.get_metadata().known_schema_issues or ""
        assert "absence" in issues.lower()


class TestQueryConstruction:
    def test_query_is_bounded_by_the_study_bbox(self, connector: OsmPowerConnector) -> None:
        query = connector.build_query()
        assert "33.16,-111.98,33.52,-111.35" in query
        assert '["power"="substation"]' in query

    def test_discovery_issues_exactly_one_request(self, connector: OsmPowerConnector) -> None:
        """Overpass is donated infrastructure; one bounded query per run is the budget."""
        from helios_connectors.types import DateRange

        result = connector.discover(DateRange())
        assert len(result.items) == 1


class TestParse:
    def test_parses_all_power_elements(
        self, connector: OsmPowerConnector, raw_document: RawDocument
    ) -> None:
        result = connector.parse(raw_document)
        assert result.ok
        assert result.document is not None
        assert len(result.document.records) == 697

    def test_surfaces_overpass_remark_as_warning(
        self, connector: OsmPowerConnector, raw_document: RawDocument
    ) -> None:
        """Overpass reports truncation in `remark` while still returning HTTP 200."""
        truncated = RawDocument(
            item=raw_document.item,
            payload=b'{"elements": [], "remark": "runtime error: Query timed out"}',
            mime_type="application/json",
            retrieved_at=raw_document.retrieved_at,
        )
        result = connector.parse(truncated)
        assert result.ok
        assert result.document is not None
        assert any("timed out" in w for w in result.document.warnings)

    def test_rejects_payload_without_elements(
        self, connector: OsmPowerConnector, raw_document: RawDocument
    ) -> None:
        broken = RawDocument(
            item=raw_document.item,
            payload=b'{"remark": "rate limited"}',
            mime_type="application/json",
            retrieved_at=raw_document.retrieved_at,
        )
        result = connector.parse(broken)
        assert not result.ok


class TestNormalize:
    @pytest.fixture
    def records(self, connector: OsmPowerConnector, raw_document: RawDocument) -> list:
        parsed = connector.parse(raw_document)
        assert parsed.document is not None
        return connector.normalize(parsed.document).records

    def test_separates_substations_from_lines(self, records: list) -> None:
        kinds = {r.entity_type for r in records}
        assert kinds == {"substation", "transmission_line"}

    def test_normalizes_multi_voltage_substation(self, records: list) -> None:
        greenbone = _by_name(records, "Greenbone Substation")
        assert greenbone.payload["max_voltage_kv"] == 500.0
        assert greenbone.payload["voltages_kv"] == ["500.0", "230.0", "69.0"]
        assert greenbone.payload["operator_name"] == "Salt River Project"

    def test_emits_point_geometry(self, records: list) -> None:
        greenbone = _by_name(records, "Greenbone Substation")
        assert greenbone.geometry_wkt is not None
        assert greenbone.geometry_wkt.startswith("POINT(")

    def test_links_back_to_openstreetmap_for_verification(self, records: list) -> None:
        greenbone = _by_name(records, "Greenbone Substation")
        assert greenbone.payload["osm_url"].startswith("https://www.openstreetmap.org/")

    def test_unknown_voltage_is_marked_unknown_not_zero(self, records: list) -> None:
        """A missing voltage must not silently become a number."""
        unknown = [
            r
            for r in records
            if r.entity_type == "substation" and r.payload["max_voltage_kv"] is None
        ]
        assert unknown, "fixture should contain at least one untagged substation"
        field = next(f for f in unknown[0].fields if f.name == "max_voltage_kv")
        assert field.assertion_class is AssertionClass.UNKNOWN
        assert field.confidence == 0.0

    def test_drops_distribution_voltage_lines(
        self, connector: OsmPowerConnector, raw_document: RawDocument
    ) -> None:
        parsed = connector.parse(raw_document)
        assert parsed.document is not None
        records = connector.normalize(parsed.document).records
        lines = [r for r in records if r.entity_type == "transmission_line"]
        assert all(r.payload["voltage_kv"] >= 115.0 for r in lines)

    def test_all_records_validate(self, connector: OsmPowerConnector, records: list) -> None:
        for record in records:
            assert connector.validate(record).valid


def _by_name(records: list, name: str):
    for record in records:
        if record.payload.get("name") == name:
            return record
    raise AssertionError(f"No record named {name!r}")
