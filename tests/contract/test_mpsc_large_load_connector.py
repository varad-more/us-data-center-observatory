"""Contract tests for the Michigan large-load disclosure connector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from helios_common.vocabulary import AssertionClass, ConnectorStatus
from helios_connectors.mpsc_large_load import MPSC_U_21990_URL, MpscLargeLoadConnector
from helios_connectors.replay import build_fixture_connector
from helios_connectors.types import DateRange, RawDocument, SourceItem
from helios_domain.ontology import StageEvidenceKind
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.contract


@pytest.fixture
def connector() -> MpscLargeLoadConnector:
    return MpscLargeLoadConnector()


@pytest.fixture
def raw_document() -> RawDocument:
    return RawDocument(
        item=SourceItem(
            source_native_id="mpsc:U-21990:2025-12-18",
            url=MPSC_U_21990_URL,
            document_type="mpsc_large_load_disclosure_html",
        ),
        payload=load_fixture_bytes("mpsc_large_load", "u-21990.html"),
        mime_type="text/html",
        retrieved_at=datetime(2026, 7, 29, tzinfo=UTC),
        http_status=200,
    )


def test_metadata_declares_a_live_but_curated_source(
    connector: MpscLargeLoadConnector,
) -> None:
    metadata = connector.get_metadata()
    assert metadata.status == ConnectorStatus.IMPLEMENTED
    assert "reviewed URL list" in (metadata.known_schema_issues or "")


def test_discovery_respects_date_windows(connector: MpscLargeLoadConnector) -> None:
    assert len(connector.discover(DateRange()).items) == 1
    assert connector.discover(DateRange(end=datetime(2025, 1, 1).date())).items == []


def test_fixture_replay_retains_official_source_url() -> None:
    connector = build_fixture_connector("mpsc-large-load-contracts")
    try:
        result = connector.discover(DateRange())
    finally:
        connector.close()

    assert result.items[0].url == MPSC_U_21990_URL


def test_normalizes_reported_load_without_geometry(
    connector: MpscLargeLoadConnector,
    raw_document: RawDocument,
) -> None:
    parsed = connector.parse(raw_document)
    assert parsed.ok and parsed.document is not None

    normalized = connector.normalize(parsed.document)
    assert normalized.error is None
    assert len(normalized.records) == 1

    record = normalized.records[0]
    assert record.geometry_wkt is None
    assert record.payload["attributes"]["location_precision"] == "township"
    assert record.payload["attributes"]["reported_load_mw"] == 1383.0

    evidence = record.evidence[0]
    assert evidence.kind == str(StageEvidenceKind.LARGE_LOAD_SERVICE_CONTRACT)
    capacity = next(field for field in evidence.fields if field.name == "reported_load_mw")
    assert capacity.assertion_class == AssertionClass.REPORTED
    assert capacity.raw_text == "1,383- megawatt (MW) data center in Saline Township"


def test_parser_fails_closed_when_the_load_phrase_disappears(
    connector: MpscLargeLoadConnector,
    raw_document: RawDocument,
) -> None:
    changed = RawDocument(
        item=raw_document.item,
        payload=b"<html><body>Case No. U-21990 without a load figure</body></html>",
        mime_type="text/html",
        retrieved_at=raw_document.retrieved_at,
    )
    result = connector.parse(changed)
    assert not result.ok
    assert "no longer contains" in (result.error or "")
