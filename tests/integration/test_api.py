"""API tests against a real database.

These assert the guarantees a consumer of the API is entitled to rely on:
provenance travels with every evidence record, redacted owner names never
appear, operator attribution is never asserted, and admin routes are closed by
default.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.types import (
    DateRange,
    DiscoveryResult,
    FetchResult,
    RawDocument,
    SourceItem,
)
from helios_domain.models import Site
from helios_geospatial.site_builder import build_sites
from helios_scoring.service import recalculate_site
from tests.conftest import load_fixture_bytes

pytestmark = pytest.mark.integration

EAST_VALLEY_CITIES = ("Mesa", "Chandler", "Tempe", "Gilbert", "Queen Creek", "Apache Junction")


def _replay(connector_cls, fixture_parts, native_id):  # noqa: ANN001, ANN202
    content = load_fixture_bytes(*fixture_parts)

    class _Replay(connector_cls):  # type: ignore[valid-type, misc]
        def discover(self, date_range: DateRange) -> DiscoveryResult:
            return DiscoveryResult(
                items=[
                    SourceItem(
                        source_native_id=native_id,
                        url="https://example.invalid/recorded",
                        document_type="fixture",
                    )
                ]
            )

        def fetch(self, item: SourceItem) -> FetchResult:
            return FetchResult(
                document=RawDocument(
                    item=item,
                    payload=content,
                    mime_type="application/json",
                    retrieved_at=datetime(2026, 7, 25, tzinfo=UTC),
                    http_status=200,
                )
            )

    return _Replay()


@pytest.fixture
def api_client(registered_sources: Session, settings, monkeypatch) -> Iterator[TestClient]:  # noqa: ANN001
    """A TestClient whose requests share the test's transactional session."""
    store = FilesystemEvidenceStore(settings.evidence_root)
    for connector in (
        _replay(
            MaricopaAssessorConnector,
            ("maricopa_assessor", "east_valley_data_centers.json"),
            "parcels",
        ),
        _replay(OsmPowerConnector, ("osm_power", "east_valley_power.json"), "power"),
    ):
        IngestionPipeline(registered_sources, connector, store, mode="fixture").run()

    build_sites(registered_sources, region_cities=EAST_VALLEY_CITIES)
    for site in registered_sources.scalars(select(Site)).all():
        recalculate_site(registered_sources, site)
    registered_sources.flush()

    from helios_api.deps import db_session
    from helios_api.main import create_app

    app = create_app()
    app.dependency_overrides[db_session] = lambda: registered_sources

    with TestClient(app) as client:
        yield client


@pytest.fixture
def site_id(api_client: TestClient) -> str:
    response = api_client.get("/sites", params={"limit": 50})
    items = response.json()["items"]
    mesa = next(i for i in items if i["project_code"] == "AZ-MESA-001")
    return str(mesa["id"])


class TestHealth:
    def test_health_does_not_require_the_database(self, api_client: TestClient) -> None:
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ready_reports_postgis(self, api_client: TestClient) -> None:
        response = api_client.get("/ready")
        assert response.status_code == 200
        assert "postgis" in response.json()["checks"]


class TestSiteList:
    def test_returns_paginated_sites(self, api_client: TestClient) -> None:
        payload = api_client.get("/sites", params={"limit": 5}).json()
        assert payload["meta"]["total"] >= 1
        assert len(payload["items"]) <= 5

    def test_never_asserts_an_operator(self, api_client: TestClient) -> None:
        payload = api_client.get("/sites", params={"limit": 100}).json()
        assert all(item["operator_status"] == "not_established" for item in payload["items"])

    def test_carries_assertion_class_for_site_kind(self, api_client: TestClient) -> None:
        payload = api_client.get("/sites", params={"limit": 5}).json()
        valid = {"reported", "extracted", "calculated", "inferred", "predicted", "unknown"}
        assert all(item["site_kind_assertion"] in valid for item in payload["items"])

    def test_filters_by_minimum_confidence(self, api_client: TestClient) -> None:
        unfiltered = api_client.get("/sites", params={"limit": 100}).json()
        assert unfiltered["items"], "fixture should produce scored sites"

        filtered = api_client.get("/sites", params={"min_confidence": 100}).json()
        assert filtered["items"] == []

    def test_rejects_out_of_range_confidence(self, api_client: TestClient) -> None:
        assert api_client.get("/sites", params={"min_confidence": 200}).status_code == 422

    def test_filters_by_bounding_box(self, api_client: TestClient) -> None:
        inside = api_client.get("/sites", params={"bbox": "-111.98,33.16,-111.35,33.52"})
        outside = api_client.get("/sites", params={"bbox": "-110.1,32.0,-110.0,32.1"})
        assert inside.json()["meta"]["total"] > 0
        assert outside.json()["meta"]["total"] == 0

    @pytest.mark.parametrize(
        "bbox",
        ["1,2,3", "a,b,c,d", "10,10,5,5", "-999,0,0,10"],
    )
    def test_rejects_malformed_bounding_boxes(
        self, api_client: TestClient, bbox: str
    ) -> None:
        assert api_client.get("/sites", params={"bbox": bbox}).status_code == 422

    def test_sorting_is_validated(self, api_client: TestClient) -> None:
        assert api_client.get("/sites", params={"sort": "-confidence"}).status_code == 200
        assert api_client.get("/sites", params={"sort": "drop table"}).status_code == 422

    def test_page_size_is_capped(self, api_client: TestClient) -> None:
        assert api_client.get("/sites", params={"limit": 10_000}).status_code == 422


class TestSiteDetail:
    def test_returns_full_profile(self, api_client: TestClient, site_id: str) -> None:
        payload = api_client.get(f"/sites/{site_id}").json()
        assert payload["project_code"] == "AZ-MESA-001"
        assert payload["parcels"]
        assert payload["boundary"]["type"] in {"Polygon", "MultiPolygon"}

    def test_includes_licence_attributions(
        self, api_client: TestClient, site_id: str
    ) -> None:
        """ODbL makes attribution a condition of use, so it travels with the data."""
        payload = api_client.get(f"/sites/{site_id}").json()
        assert payload["attributions"]
        assert any("Maricopa" in a for a in payload["attributions"])

    def test_includes_an_explained_prediction(
        self, api_client: TestClient, site_id: str
    ) -> None:
        prediction = api_client.get(f"/sites/{site_id}").json()["latest_prediction"]
        assert prediction is not None
        assert prediction["explanations"]
        for explanation in prediction["explanations"]:
            assert explanation["rule_id"]
            assert explanation["label"]

    def test_shell_indicators_are_flagged_without_attribution(
        self, api_client: TestClient, site_id: str
    ) -> None:
        organizations = api_client.get(f"/sites/{site_id}").json()["organizations"]
        platypus = next(
            o for o in organizations if o["canonical_name"] == "PLATYPUS DEVELOPMENT LLC"
        )
        assert platypus["is_suspected_shell"] is True
        assert "do not constitute an attribution" in platypus["attribution_note"]

    def test_unknown_site_returns_404(self, api_client: TestClient) -> None:
        response = api_client.get("/sites/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestTimeline:
    def test_returns_chronological_entries(
        self, api_client: TestClient, site_id: str
    ) -> None:
        entries = api_client.get(f"/sites/{site_id}/timeline").json()["entries"]
        assert len(entries) >= 5
        dates = [e["occurred_on"] for e in entries]
        assert dates == sorted(dates)

    def test_interleaves_evidence_and_stage_transitions(
        self, api_client: TestClient, site_id: str
    ) -> None:
        entries = api_client.get(f"/sites/{site_id}/timeline").json()["entries"]
        kinds = {e["entry_type"] for e in entries}
        assert "evidence" in kinds
        assert "stage_transition" in kinds

    def test_every_evidence_entry_carries_full_provenance(
        self, api_client: TestClient, site_id: str
    ) -> None:
        """The product claim is traceability; this is the contract test for it."""
        entries = api_client.get(f"/sites/{site_id}/timeline").json()["entries"]
        evidence_entries = [e for e in entries if e["entry_type"] == "evidence"]
        assert evidence_entries

        for entry in evidence_entries:
            source = entry["evidence"]["source"]
            assert source["document_id"]
            assert source["document_version_id"]
            assert source["source_url"].startswith("http")
            assert len(source["content_sha256"]) == 64
            assert source["retrieved_at"]
            assert entry["evidence"]["snippet"]
            assert entry["evidence"]["observed_at"]


class TestEvidenceEndpoint:
    def test_lists_evidence_with_paging(
        self, api_client: TestClient, site_id: str
    ) -> None:
        payload = api_client.get(f"/sites/{site_id}/evidence", params={"limit": 2}).json()
        assert payload["meta"]["total"] >= 1
        assert len(payload["items"]) <= 2

    def test_filters_by_kind(self, api_client: TestClient, site_id: str) -> None:
        payload = api_client.get(
            f"/sites/{site_id}/evidence",
            params={"kind": "assessor_data_center_classification"},
        ).json()
        assert payload["items"]
        assert all(
            i["evidence_kind"] == "assessor_data_center_classification"
            for i in payload["items"]
        )


class TestMapLayers:
    def test_sites_layer_is_valid_geojson(self, api_client: TestClient) -> None:
        payload = api_client.get("/map/sites").json()
        assert payload["type"] == "FeatureCollection"
        assert payload["features"]
        for feature in payload["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}

    def test_infrastructure_layer_carries_odbl_attribution(
        self, api_client: TestClient
    ) -> None:
        payload = api_client.get("/map/infrastructure").json()
        assert any("OpenStreetMap" in a for a in payload["attributions"])

    def test_parcel_layer_never_exposes_redacted_owners(
        self, api_client: TestClient
    ) -> None:
        payload = api_client.get("/map/parcels").json()
        for feature in payload["features"]:
            properties = feature["properties"]
            if properties["owner_is_redacted"]:
                assert properties["owner_name"] is None


class TestSourceRegistry:
    def test_publishes_inaccessible_sources_with_reasons(
        self, api_client: TestClient
    ) -> None:
        """Publishing the gaps is what distinguishes 'no activity' from 'no access'."""
        payload = api_client.get("/sources").json()
        blocked = [s for s in payload["items"] if s["connector_status"] == "fixture_only"]
        assert blocked
        assert all(s["access_limitation"] for s in blocked)

    def test_reports_coverage_summary(self, api_client: TestClient) -> None:
        payload = api_client.get("/sources").json()
        assert payload["coverage_summary"]
        assert payload["coverage_summary"].get("implemented", 0) >= 2


class TestAnalytics:
    def test_stage_distribution_covers_every_stage(self, api_client: TestClient) -> None:
        payload = api_client.get("/analytics/stages").json()
        assert len(payload["stages"]) == 9

    def test_provenance_completeness_is_total(self, api_client: TestClient) -> None:
        """The headline guarantee, measured rather than asserted."""
        payload = api_client.get("/analytics/provenance").json()
        assert payload["total_evidence_records"] > 0
        assert payload["completeness_ratio"] == 1.0


class TestExports:
    def test_csv_export_has_a_header_and_rows(self, api_client: TestClient) -> None:
        response = api_client.get("/exports/sites.csv")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        lines = response.text.strip().splitlines()
        assert lines[0].startswith("project_code,")
        assert len(lines) > 1

    def test_geojson_export_carries_attribution_and_disclaimer(
        self, api_client: TestClient
    ) -> None:
        payload = json.loads(api_client.get("/exports/sites.geojson").text)
        assert payload["type"] == "FeatureCollection"
        assert payload["metadata"]["attributions"]
        assert "not fact" in payload["metadata"]["disclaimer"]

    def test_evidence_bundle_is_verifiable(
        self, api_client: TestClient, site_id: str
    ) -> None:
        """The bundle must let a sceptic check Helios without trusting Helios."""
        response = api_client.get(f"/exports/site/{site_id}/bundle.zip")
        assert response.status_code == 200

        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            assert {"evidence.json", "manifest.json", "parcels.csv", "README.txt"} <= names

            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["documents"]
            for document in manifest["documents"]:
                assert document["source_url"]
                for version in document["versions"]:
                    assert len(version["content_sha256"]) == 64

            evidence = json.loads(archive.read("evidence.json"))
            assert evidence["scoring_model"]["parameters"]["rules"]
            assert evidence["site"]["operator_status"] == "not_established"
            assert evidence["evidence"]


class TestAdminAuthorization:
    def test_admin_routes_are_refused_when_no_token_is_configured(
        self, api_client: TestClient
    ) -> None:
        """Defaulting to open would mean a misconfigured deployment exposes writes."""
        response = api_client.post("/admin/sites/rebuild")
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]

    def test_admin_routes_reject_a_wrong_token(
        self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from helios_common.config import get_settings

        monkeypatch.setenv("HELIOS_ADMIN_API_TOKEN", "correct-token")
        get_settings.cache_clear()

        response = api_client.post(
            "/admin/sites/rebuild", headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401

    def test_admin_routes_accept_the_configured_token(
        self, api_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from helios_common.config import get_settings

        monkeypatch.setenv("HELIOS_ADMIN_API_TOKEN", "correct-token")
        get_settings.cache_clear()

        response = api_client.post(
            "/admin/sites/rebuild", headers={"Authorization": "Bearer correct-token"}
        )
        assert response.status_code == 200


class TestOpenApi:
    def test_specification_is_generated(self, api_client: TestClient) -> None:
        spec = api_client.get("/openapi.json").json()
        assert spec["info"]["title"]
        assert len(spec["paths"]) >= 20

    def test_documents_the_assertion_vocabulary(self, api_client: TestClient) -> None:
        """The epistemic contract belongs in the published API description."""
        spec = api_client.get("/openapi.json").json()
        description = spec["info"]["description"]
        for term in ("reported", "extracted", "inferred", "predicted", "unknown"):
            assert term in description
