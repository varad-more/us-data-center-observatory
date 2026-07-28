"""Contract tests for the published area-total connectors.

The values asserted here were read off the agencies' own files and cross-checked
against their published summaries. They are pinned deliberately: these figures
are the reported denominator every inferred site estimate is shown against, so a
silent parser regression that halved them would make Helios's own numbers look
twice as significant as they are.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import AssertionClass, ConnectorStatus, ExtractionMethod
from helios_connectors.area_totals import (
    CAPACITY_ROLLUP_FUEL,
    CAPACITY_ROLLUP_PRODUCER,
    EiaStateElectricityConnector,
    EiaStateGenerationCapacityConnector,
    UsgsCountyWaterConnector,
    _clean_number,
    _read_eia_workbook,
)
from helios_connectors.types import DateRange, RawDocument, SourceItem
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract

WATER_FIXTURE = ("usgs_water", "arizona_counties_2015.csv")
ELECTRICITY_FIXTURE = ("eia_electricity", "sales_annual.xlsx")
CAPACITY_FIXTURE = ("eia_generation", "existcapacity_annual.xlsx")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MARICOPA = "04013"
PINAL = "04021"


def _raw(parts: tuple[str, ...], mime_type: str) -> RawDocument:
    return RawDocument(
        item=SourceItem(
            source_native_id="area-totals:test",
            url="https://example.invalid/recorded",
            document_type="area_totals_table",
        ),
        payload=load_fixture_bytes(*parts),
        mime_type=mime_type,
        retrieved_at=datetime(2026, 7, 28, tzinfo=UTC),
        http_status=200,
    )


@pytest.fixture
def water() -> UsgsCountyWaterConnector:
    return UsgsCountyWaterConnector(counties=(MARICOPA, PINAL))


@pytest.fixture
def electricity() -> EiaStateElectricityConnector:
    return EiaStateElectricityConnector(states=("AZ",))


def _by_metric(rows: list[dict], area_code: str) -> dict[str, dict]:
    return {r["metric"]: r for r in rows if r["area_code"] == area_code}


class TestNumberCleaning:
    @pytest.mark.parametrize("placeholder", ["", "-", "--", "NA", "N/A", "NM", "W", "*"])
    def test_agency_placeholders_are_not_zero(self, placeholder: str) -> None:
        """A withheld figure must read as absent, never as a measured zero."""
        assert _clean_number(placeholder) is None

    def test_thousands_separators_survive(self) -> None:
        assert _clean_number("2,058.19") == pytest.approx(2058.19)


class TestUsgsCountyWater:
    def test_is_implemented(self, water: UsgsCountyWaterConnector) -> None:
        assert water.get_metadata().status == ConnectorStatus.IMPLEMENTED

    def test_reference_year_is_2015(self, water: UsgsCountyWaterConnector) -> None:
        """2015 is the newest county-level release that exists, not a stale pin."""
        assert water.reference_year == 2015

    def test_discovery_is_one_file(self, water: UsgsCountyWaterConnector) -> None:
        result = water.discover(DateRange())
        assert len(result.items) == 1
        assert result.items[0].hints["reference_year"] == 2015

    def test_parses_the_published_maricopa_figures(self, water: UsgsCountyWaterConnector) -> None:
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.ok and parsed.document is not None
        metrics = _by_metric(parsed.document.records, MARICOPA)

        assert metrics["public_supply_water_withdrawal"]["value"] == pytest.approx(776.54)
        assert metrics["industrial_water_withdrawal"]["value"] == pytest.approx(1.81)
        assert metrics["thermoelectric_water_withdrawal"]["value"] == pytest.approx(24.08)
        assert metrics["total_water_withdrawal"]["value"] == pytest.approx(2058.19)
        assert metrics["total_water_withdrawal"]["unit"] == "Mgal/d"

    def test_population_is_rescaled_from_thousands_to_people(
        self, water: UsgsCountyWaterConnector
    ) -> None:
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        population = _by_metric(parsed.document.records, MARICOPA)["population"]
        assert population["value"] == pytest.approx(4_167_947)
        assert population["unit"] == "people"

    def test_county_filter_excludes_the_rest_of_the_state(
        self, water: UsgsCountyWaterConnector
    ) -> None:
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        assert {r["area_code"] for r in parsed.document.records} == {MARICOPA, PINAL}

    def test_unfiltered_reads_every_county_in_the_file(self) -> None:
        """The fixture is an Arizona excerpt; unfiltered, all 15 counties parse."""
        connector = UsgsCountyWaterConnector()
        parsed = connector.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        assert len({r["area_code"] for r in parsed.document.records}) == 15

    def test_rows_are_county_scoped(self, water: UsgsCountyWaterConnector) -> None:
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        assert {r["area_kind"] for r in parsed.document.records} == {"county"}


class TestEiaStateElectricity:
    def test_is_implemented(self, electricity: EiaStateElectricityConnector) -> None:
        assert electricity.get_metadata().status == ConnectorStatus.IMPLEMENTED

    def test_parses_the_published_arizona_figures(
        self, electricity: EiaStateElectricityConnector
    ) -> None:
        parsed = electricity.parse(
            _raw(
                ELECTRICITY_FIXTURE,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        assert parsed.ok and parsed.document is not None
        sectors = {r["sector"]: r for r in parsed.document.records}

        assert sectors["residential"]["value"] == pytest.approx(38_707_416)
        assert sectors["commercial"]["value"] == pytest.approx(29_128_178)
        assert sectors["industrial"]["value"] == pytest.approx(14_113_139)
        assert sectors["transportation"]["value"] == pytest.approx(11_341)
        assert sectors["total"]["value"] == pytest.approx(81_960_074)
        assert sectors["total"]["unit"] == "MWh/yr"

    def test_sectors_sum_to_the_published_total(
        self, electricity: EiaStateElectricityConnector
    ) -> None:
        """Only 'Total Electric Industry' rows are read, so the parts add up.

        Reading every provider category would double count, and the failure mode
        is silent: the numbers would still look plausible, just inflated.
        """
        parsed = electricity.parse(
            _raw(
                ELECTRICITY_FIXTURE,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        assert parsed.document is not None
        sectors = {r["sector"]: r["value"] for r in parsed.document.records}
        parts = sum(v for k, v in sectors.items() if k != "total")
        assert parts == pytest.approx(sectors["total"], rel=1e-6)

    def test_rows_are_state_scoped_not_county(
        self, electricity: EiaStateElectricityConnector
    ) -> None:
        """The granularity gap against the water totals must stay visible."""
        parsed = electricity.parse(
            _raw(
                ELECTRICITY_FIXTURE,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        assert parsed.document is not None
        assert {r["area_kind"] for r in parsed.document.records} == {"state"}

    def test_resolves_the_latest_year_when_none_requested(
        self, electricity: EiaStateElectricityConnector
    ) -> None:
        electricity.parse(
            _raw(
                ELECTRICITY_FIXTURE,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        assert electricity.reference_year == 2020

    def test_honours_an_explicit_year(self) -> None:
        connector = EiaStateElectricityConnector(states=("AZ",), year=2010)
        parsed = connector.parse(
            _raw(
                ELECTRICITY_FIXTURE,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        )
        assert parsed.document is not None
        assert connector.reference_year == 2010
        assert {r["reference_year"] for r in parsed.document.records} == {2010}

    def test_rejects_a_payload_that_is_not_a_workbook(
        self, electricity: EiaStateElectricityConnector
    ) -> None:
        """EIA soft-404s serve an HTML page with HTTP 200; that must not parse."""
        document = _raw(
            ELECTRICITY_FIXTURE,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        document = RawDocument(
            item=document.item,
            payload=b"<!DOCTYPE html><html><body>Page not found</body></html>",
            mime_type="text/html",
            retrieved_at=document.retrieved_at,
            http_status=200,
        )
        parsed = electricity.parse(document)
        assert not parsed.ok
        assert parsed.error is not None and "xlsx" in parsed.error


class TestNormalization:
    def test_every_area_total_is_reported_not_inferred(
        self, water: UsgsCountyWaterConnector
    ) -> None:
        """These are figures an agency measured. Helios derived none of them."""
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        result = water.normalize(parsed.document)

        assert result.records
        for record in result.records:
            assert record.entity_type == "area_total"
            assert len(record.fields) == 1
            field = record.fields[0]
            assert field.assertion_class == AssertionClass.REPORTED
            assert field.extraction_method == ExtractionMethod.TABLE_PARSE

    def test_native_id_identifies_the_measurement_not_the_file(
        self, water: UsgsCountyWaterConnector
    ) -> None:
        """Re-ingesting a republished file must overwrite, not accumulate."""
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        result = water.normalize(parsed.document)

        ids = [r.source_native_id for r in result.records]
        assert len(ids) == len(set(ids))
        assert f"county:{MARICOPA}:total_water_withdrawal:all:2015" in ids

    def test_no_evidence_is_emitted_for_an_area_figure(
        self, water: UsgsCountyWaterConnector
    ) -> None:
        """Evidence in Helios is a claim about a site; a county total is not one."""
        parsed = water.parse(_raw(WATER_FIXTURE, "text/csv"))
        assert parsed.document is not None
        result = water.normalize(parsed.document)
        assert all(not record.evidence for record in result.records)


@pytest.fixture
def capacity() -> EiaStateGenerationCapacityConnector:
    return EiaStateGenerationCapacityConnector(states=("AZ",))


class TestEiaStateGenerationCapacity:
    def test_is_implemented(self, capacity: EiaStateGenerationCapacityConnector) -> None:
        assert capacity.get_metadata().status == ConnectorStatus.IMPLEMENTED

    def test_parses_the_published_arizona_capacity(
        self, capacity: EiaStateGenerationCapacityConnector
    ) -> None:
        parsed = capacity.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.ok and parsed.document is not None
        metrics = {r["metric"]: r for r in parsed.document.records}

        assert metrics["generation_nameplate_capacity"]["value"] == pytest.approx(36_344.9)
        assert metrics["generation_summer_capacity"]["value"] == pytest.approx(32_876.5)
        assert metrics["generation_nameplate_capacity"]["unit"] == "MW"

    def test_summer_capacity_is_below_nameplate(
        self, capacity: EiaStateGenerationCapacityConnector
    ) -> None:
        """Not a formality. Nameplate overstates what an Arizona grid can deliver
        on the afternoon that decides whether there is room, which is why the
        comparison uses summer capacity rather than the more-quoted figure."""
        parsed = capacity.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        metrics = {r["metric"]: r["value"] for r in parsed.document.records}
        assert metrics["generation_summer_capacity"] < metrics["generation_nameplate_capacity"]

    def test_keeps_only_the_rollup_row(self, capacity: EiaStateGenerationCapacityConnector) -> None:
        """Producer type and fuel source each carry a roll-up beside their parts.

        Reading the sheet naively sums a state several times over and the result
        still looks like a capacity figure, just a wrong one.
        """
        parsed = capacity.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        assert len(parsed.document.records) == 2  # two metrics, one area, one year

    def test_the_kept_row_equals_the_sum_of_the_parts_it_rolls_up(
        self, capacity: EiaStateGenerationCapacityConnector
    ) -> None:
        """Proves the roll-up was picked rather than one fuel that happened to
        parse. Read straight from the fixture, independently of the connector."""
        records = _read_eia_workbook(
            load_fixture_bytes(*CAPACITY_FIXTURE), ("Year", "State Code"), label="capacity"
        )
        parsed = capacity.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        year = parsed.document.records[0]["reference_year"]

        arizona = [
            r
            for r in records
            if str(r["State Code"]).strip() == "AZ"
            and int(r["Year"]) == year
            and str(r["Producer Type"]).strip() == CAPACITY_ROLLUP_PRODUCER
        ]
        parts = sum(
            r["Nameplate Capacity (Megawatts)"]
            for r in arizona
            if str(r["Fuel Source"]).strip() != CAPACITY_ROLLUP_FUEL
        )
        emitted = next(
            r["value"]
            for r in parsed.document.records
            if r["metric"] == "generation_nameplate_capacity"
        )
        assert emitted == pytest.approx(parts)

    def test_state_filter_excludes_the_rest_of_the_country(
        self, capacity: EiaStateGenerationCapacityConnector
    ) -> None:
        parsed = capacity.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        assert {r["area_code"] for r in parsed.document.records} == {"AZ"}

    def test_unfiltered_reads_every_state_in_the_file(self) -> None:
        connector = EiaStateGenerationCapacityConnector()
        parsed = connector.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        assert len({r["area_code"] for r in parsed.document.records}) == 51

    def test_honours_an_explicit_year(self) -> None:
        connector = EiaStateGenerationCapacityConnector(states=("AZ",), year=2023)
        parsed = connector.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        assert connector.reference_year == 2023
        assert {r["reference_year"] for r in parsed.document.records} == {2023}

    def test_rejects_a_payload_that_is_not_a_workbook(
        self, capacity: EiaStateGenerationCapacityConnector
    ) -> None:
        document = _raw(CAPACITY_FIXTURE, XLSX_MIME)
        document = RawDocument(
            item=document.item,
            payload=b"<!DOCTYPE html><html><body>Page not found</body></html>",
            mime_type="text/html",
            retrieved_at=document.retrieved_at,
            http_status=200,
        )
        parsed = capacity.parse(document)
        assert not parsed.ok
        assert parsed.error is not None and "xlsx" in parsed.error

    def test_capacity_is_reported_like_every_other_area_total(
        self, capacity: EiaStateGenerationCapacityConnector
    ) -> None:
        parsed = capacity.parse(_raw(CAPACITY_FIXTURE, XLSX_MIME))
        assert parsed.document is not None
        result = capacity.normalize(parsed.document)

        assert result.records
        for record in result.records:
            assert record.entity_type == "area_total"
            assert record.fields[0].assertion_class == AssertionClass.REPORTED
