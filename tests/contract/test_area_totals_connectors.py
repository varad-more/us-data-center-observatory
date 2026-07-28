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
    EiaStateElectricityConnector,
    UsgsCountyWaterConnector,
    _clean_number,
)
from helios_connectors.types import DateRange, RawDocument, SourceItem
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract

WATER_FIXTURE = ("usgs_water", "arizona_counties_2015.csv")
ELECTRICITY_FIXTURE = ("eia_electricity", "sales_annual.xlsx")

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
