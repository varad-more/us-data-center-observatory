"""Contract tests for the Maricopa County Assessor connector.

Exercised against a payload captured verbatim from the live ArcGIS service on
2026-07-25 (query: East Valley cities where ``PropertyUseDescription='DATA
CENTERS'``). Using a recorded response rather than the live service means these
tests assert connector behaviour, not county server availability.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import AssertionClass
from helios_connectors.maricopa_assessor import (
    MaricopaAssessorConnector,
    normalize_apn,
)
from helios_connectors.types import RawDocument, SourceItem
from helios_domain.ontology import StageEvidenceKind
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract

FIXTURE = ("maricopa_assessor", "east_valley_data_centers.json")


@pytest.fixture
def raw_document() -> RawDocument:
    """The recorded assessor response wrapped as a fetched document."""
    return RawDocument(
        item=SourceItem(
            source_native_id="parcel-query:test:offset:0",
            url="https://gis.maricopa.gov/arcgis/rest/services/RED/Assessor/MapServer/1/query",
            document_type="arcgis_query_page",
        ),
        payload=load_fixture_bytes(*FIXTURE),
        mime_type="application/json",
        retrieved_at=datetime(2026, 7, 25, 21, 26, tzinfo=UTC),
        http_status=200,
    )


@pytest.fixture
def connector() -> MaricopaAssessorConnector:
    return MaricopaAssessorConnector()


class TestApnNormalization:
    def test_preserves_alpha_suffix(self) -> None:
        """Split parcels carry alpha suffixes; dropping them merges distinct parcels."""
        assert normalize_apn("304-33-005S") == "30433005S"
        assert normalize_apn("30433005S") == "30433005S"

    def test_distinguishes_suffixed_from_unsuffixed(self) -> None:
        assert normalize_apn("304-33-005S") != normalize_apn("304-33-005")

    def test_strips_formatting_only(self) -> None:
        assert normalize_apn("139-38-089") == "13938089"


class TestMetadata:
    def test_declares_personal_data_and_attribution(
        self, connector: MaricopaAssessorConnector
    ) -> None:
        metadata = connector.get_metadata()
        assert metadata.contains_personal_data is True
        assert metadata.attribution_required is True
        assert metadata.attribution_text


class TestParse:
    def test_parses_every_feature(
        self, connector: MaricopaAssessorConnector, raw_document: RawDocument
    ) -> None:
        result = connector.parse(raw_document)
        assert result.ok
        assert result.document is not None
        assert len(result.document.records) == 14

    def test_assigns_json_path_locators(
        self, connector: MaricopaAssessorConnector, raw_document: RawDocument
    ) -> None:
        """Locators are how the UI points a user at the exact bytes behind a fact."""
        result = connector.parse(raw_document)
        assert result.document is not None
        assert result.document.records[0]["_locator"] == "$.features[0]"

    def test_computes_field_signature_for_drift_detection(
        self, connector: MaricopaAssessorConnector, raw_document: RawDocument
    ) -> None:
        result = connector.parse(raw_document)
        assert result.document is not None
        assert result.document.field_signature

    def test_reports_service_errors_rather_than_raising(
        self, connector: MaricopaAssessorConnector, raw_document: RawDocument
    ) -> None:
        broken = RawDocument(
            item=raw_document.item,
            payload=b'{"error": {"code": 400, "message": "Failed to execute query."}}',
            mime_type="application/json",
            retrieved_at=raw_document.retrieved_at,
        )
        result = connector.parse(broken)
        assert not result.ok
        assert result.error is not None
        assert "Service error" in result.error

    def test_reports_invalid_json(
        self, connector: MaricopaAssessorConnector, raw_document: RawDocument
    ) -> None:
        broken = RawDocument(
            item=raw_document.item,
            payload=b"<html>gateway timeout</html>",
            mime_type="application/json",
            retrieved_at=raw_document.retrieved_at,
        )
        result = connector.parse(broken)
        assert not result.ok
        assert result.error is not None
        assert "Invalid JSON" in result.error


class TestNormalize:
    @pytest.fixture
    def records(self, connector: MaricopaAssessorConnector, raw_document: RawDocument) -> list:
        parsed = connector.parse(raw_document)
        assert parsed.document is not None
        result = connector.normalize(parsed.document)
        assert result.rejected == 0
        return result.records

    def test_normalizes_all_parcels(self, records: list) -> None:
        assert len(records) == 14
        assert all(r.entity_type == "parcel" for r in records)

    def test_converts_epoch_millisecond_dates(self, records: list) -> None:
        """ArcGIS emits epoch millis; a naive int cast would land in 1970."""
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        assert platypus.payload["last_deed_date"].isoformat() == "2013-11-04"
        assert platypus.payload["last_sale_date"].isoformat() == "2013-11-01"

    def test_preserves_recorder_deep_link_for_verification(self, records: list) -> None:
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        assert "recorder.maricopa.gov" in platypus.payload["last_deed_url"]
        assert platypus.payload["last_deed_number"] == "20130962087"

    def test_separates_standing_classification_from_the_transfer_event(self, records: list) -> None:
        """One assessor row carries facts with different dates and different natures."""
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        by_kind = {e.kind: e for e in platypus.evidence}

        classification = by_kind[str(StageEvidenceKind.ASSESSOR_DATA_CENTER_CLASSIFICATION)]
        acquisition = by_kind[str(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION)]

        assert classification.is_standing_condition is True
        assert acquisition.is_standing_condition is False
        assert acquisition.observed_at.isoformat() == "2013-11-04"
        assert classification.observed_at > acquisition.observed_at

    def test_shell_ownership_evidence_is_low_confidence_and_disclaims_attribution(
        self, records: list
    ) -> None:
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        shell = next(
            e for e in platypus.evidence if e.kind == str(StageEvidenceKind.SHELL_ENTITY_OWNERSHIP)
        )
        assert shell.confidence <= 0.5
        assert shell.assertion_class is AssertionClass.INFERRED
        assert "imply no particular parent" in shell.summary

    def test_every_evidence_item_carries_a_locator_and_summary(self, records: list) -> None:
        for record in records:
            for item in record.evidence:
                assert item.locator
                assert item.summary
                assert item.observed_at is not None

    def test_produces_multipolygon_wkt(self, records: list) -> None:
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        assert platypus.geometry_wkt is not None
        assert platypus.geometry_wkt.startswith("MULTIPOLYGON((")

    def test_detects_shell_indicators_without_asserting_a_parent(self, records: list) -> None:
        """Shell signals are flags for review, never an operator claim."""
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        analysis = platypus.payload["owner_analysis"]
        assert analysis["is_suspected_shell"] is True
        assert analysis["legal_form"] == "LLC"
        assert "operator" not in platypus.payload

    def test_records_field_level_provenance(self, records: list) -> None:
        platypus = _find(records, "PLATYPUS DEVELOPMENT LLC")
        by_name = {f.name: f for f in platypus.fields}
        assert by_name["lot_size_acres"].locator.endswith("attributes.LotSize_Acre")
        assert by_name["lot_size_acres"].assertion_class is AssertionClass.REPORTED
        assert by_name["lot_size_acres"].normalized_unit == "acres"

    def test_no_natural_person_names_in_this_fixture(self, records: list) -> None:
        """Every owner in the data-center classification is an organization."""
        assert all(not r.redactions_applied for r in records)

    def test_all_records_pass_validation(
        self, connector: MaricopaAssessorConnector, records: list
    ) -> None:
        for record in records:
            result = connector.validate(record)
            assert result.valid, result.error_messages


class TestPiiRedaction:
    """Redaction is exercised with a synthetic payload; no real personal data is stored."""

    @pytest.fixture
    def residential_document(self) -> RawDocument:
        payload = b"""{
          "features": [
            {"attributes": {
              "OBJECTID": 1, "APN": "13938089", "APNDash": "139-38-089",
              "PropertyFullStreetAddress": "1 EXAMPLE ST", "PropertyCity": "MESA",
              "OwnerName": "EXAMPLEPERSON PATTERN CASE",
              "PropertyUseDescription": "SFR GRADE 010-1 URBAN SUBDIVIDED",
              "LotSize_Acre": 0.15, "DeedDate": 1720162800000},
             "geometry": {"rings": [[[-111.8,33.4],[-111.8,33.5],[-111.7,33.5],[-111.8,33.4]]]}}
          ]
        }"""
        return RawDocument(
            item=SourceItem(source_native_id="synthetic", url="https://example.invalid/query"),
            payload=payload,
            mime_type="application/json",
            retrieved_at=datetime(2026, 7, 25, tzinfo=UTC),
        )

    def test_suppresses_natural_person_owner(
        self, connector: MaricopaAssessorConnector, residential_document: RawDocument
    ) -> None:
        parsed = connector.parse(residential_document)
        assert parsed.document is not None
        record = connector.normalize(parsed.document).records[0]

        assert record.payload["owner_name_raw"] is None
        assert record.payload["owner_is_redacted"] is True
        assert record.redactions_applied == ["owner_name"]

    def test_redaction_is_disclosed_rather_than_silent(
        self, connector: MaricopaAssessorConnector, residential_document: RawDocument
    ) -> None:
        parsed = connector.parse(residential_document)
        assert parsed.document is not None
        record = connector.normalize(parsed.document).records[0]

        owner_field = next(f for f in record.fields if f.name == "owner_name")
        assert owner_field.value is None
        assert owner_field.assertion_class is AssertionClass.UNKNOWN
        assert "withheld" in (owner_field.snippet or "")

    def test_normalized_name_not_leaked_for_redacted_owner(
        self, connector: MaricopaAssessorConnector, residential_document: RawDocument
    ) -> None:
        """The normalized key would reconstruct the suppressed name, so it is dropped too."""
        parsed = connector.parse(residential_document)
        assert parsed.document is not None
        record = connector.normalize(parsed.document).records[0]
        assert record.payload["owner_analysis"]["normalized_name"] is None

    def test_ordinary_residential_parcel_generates_no_evidence(
        self, connector: MaricopaAssessorConnector, residential_document: RawDocument
    ) -> None:
        """Most of the county must produce nothing, or the signal is drowned."""
        parsed = connector.parse(residential_document)
        assert parsed.document is not None
        record = connector.normalize(parsed.document).records[0]
        assert record.evidence == []


class TestLiveFetchIsBlockedInTests:
    def test_fetch_refuses_when_live_access_disabled(
        self, connector: MaricopaAssessorConnector
    ) -> None:
        result = connector.fetch(
            SourceItem(source_native_id="x", url="https://gis.maricopa.gov/arcgis/rest/x")
        )
        assert not result.ok
        assert result.error is not None
        assert "FetchBlockedError" in result.error


def _find(records: list, owner_name: str):
    """Locate a normalized record by owner name."""
    for record in records:
        if record.payload.get("owner_name_raw") == owner_name:
            return record
    raise AssertionError(f"No record with owner {owner_name!r}")
