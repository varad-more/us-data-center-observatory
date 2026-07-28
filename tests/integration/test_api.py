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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_connectors.area_totals import (
    EiaStateElectricityConnector,
    EiaStateGenerationCapacityConnector,
    UsgsCountyWaterConnector,
)
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.registry import SOURCE_REGISTRY
from helios_connectors.replay import replay_connector as _replay
from helios_domain.models import Site
from helios_geospatial.site_builder import build_sites
from helios_scoring.service import recalculate_site

pytestmark = pytest.mark.integration


@pytest.fixture
def api_client(registered_sources: Session, settings, monkeypatch) -> Iterator[TestClient]:
    """A TestClient whose requests share the test's transactional session."""
    store = FilesystemEvidenceStore(settings.evidence_root)
    for connector in (
        _replay(
            MaricopaAssessorConnector,
            ("maricopa_assessor", "east_valley_data_centers.json"),
            "parcels",
        ),
        _replay(OsmPowerConnector, ("osm_power", "east_valley_power.json"), "power"),
        _replay(
            UsgsCountyWaterConnector,
            ("usgs_water", "arizona_counties_2015.csv"),
            "water",
            counties=("04013", "04021"),
        ),
        _replay(
            EiaStateElectricityConnector,
            ("eia_electricity", "sales_annual.xlsx"),
            "electricity",
            states=("AZ",),
        ),
        _replay(
            EiaStateGenerationCapacityConnector,
            ("eia_generation", "existcapacity_annual.xlsx"),
            "capacity",
            states=("AZ",),
        ),
    ):
        IngestionPipeline(registered_sources, connector, store, mode="fixture").run()

    build_sites(registered_sources)
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
    def test_rejects_malformed_bounding_boxes(self, api_client: TestClient, bbox: str) -> None:
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

    def test_includes_licence_attributions(self, api_client: TestClient, site_id: str) -> None:
        """ODbL makes attribution a condition of use, so it travels with the data."""
        payload = api_client.get(f"/sites/{site_id}").json()
        assert payload["attributions"]
        assert any("Maricopa" in a for a in payload["attributions"])

    def test_includes_an_explained_prediction(self, api_client: TestClient, site_id: str) -> None:
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
    def test_returns_chronological_entries(self, api_client: TestClient, site_id: str) -> None:
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
    def test_lists_evidence_with_paging(self, api_client: TestClient, site_id: str) -> None:
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
            i["evidence_kind"] == "assessor_data_center_classification" for i in payload["items"]
        )


class TestMapLayers:
    def test_sites_layer_is_valid_geojson(self, api_client: TestClient) -> None:
        payload = api_client.get("/map/sites").json()
        assert payload["type"] == "FeatureCollection"
        assert payload["features"]
        for feature in payload["features"]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] in {"Polygon", "MultiPolygon"}

    def test_infrastructure_layer_carries_odbl_attribution(self, api_client: TestClient) -> None:
        payload = api_client.get("/map/infrastructure").json()
        assert any("OpenStreetMap" in a for a in payload["attributions"])

    def test_parcel_layer_never_exposes_redacted_owners(self, api_client: TestClient) -> None:
        payload = api_client.get("/map/parcels").json()
        for feature in payload["features"]:
            properties = feature["properties"]
            if properties["owner_is_redacted"]:
                assert properties["owner_name"] is None


class TestSourceRegistry:
    def test_publishes_inaccessible_sources_with_reasons(self, api_client: TestClient) -> None:
        """Publishing the gaps is what distinguishes 'no activity' from 'no access'."""
        payload = api_client.get("/sources").json()
        blocked = [s for s in payload["items"] if s["connector_status"] == "fixture_only"]
        assert blocked
        assert all(s["access_limitation"] for s in blocked)

    def test_every_declared_limitation_reaches_the_api(self, api_client: TestClient) -> None:
        """A reason recorded in the registry is worthless if the API drops it.

        This once only held for sources that had a connector, which excluded
        every source with no access at all -- the ones the reason exists for.
        """
        items = {s["slug"]: s for s in api_client.get("/sources").json()["items"]}
        for entry in SOURCE_REGISTRY:
            if not entry.access_limitation:
                continue
            assert entry.slug in items, entry.slug
            assert items[entry.slug]["access_limitation"] == entry.access_limitation, entry.slug

    def test_status_is_the_registry_status(self, api_client: TestClient) -> None:
        """No source may report "planned" merely because it has no connector row."""
        items = {s["slug"]: s for s in api_client.get("/sources").json()["items"]}
        for entry in SOURCE_REGISTRY:
            assert items[entry.slug]["connector_status"] == str(entry.connector_status), entry.slug

    def test_withdrawn_source_is_not_mistaken_for_planned(self, api_client: TestClient) -> None:
        """HIFLD substations were taken away; nothing should imply they are coming."""
        items = {s["slug"]: s for s in api_client.get("/sources").json()["items"]}
        hifld = items["hifld-electric-substations"]
        assert hifld["connector_status"] == "withdrawn"
        assert "withdrew public access" in hifld["access_limitation"]
        assert hifld["connector_slug"] is None

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

    def test_growth_series_is_cumulative_and_monotonic(self, api_client: TestClient) -> None:
        """A site that reached stage 6 has passed stage 4 and counts at both.

        Counting only a site's current stage would make earlier stages appear to
        drain as projects advanced, which reads as decline rather than movement.
        """
        payload = api_client.get("/analytics/growth").json()
        points = payload["points"]
        assert points, "fixture corpus should produce at least one month"

        for point in points:
            counts = point["cumulative_by_stage"]
            ordered = [counts[str(stage)] for stage in sorted(int(k) for k in counts)]
            # Non-increasing as the stage threshold rises.
            assert ordered == sorted(ordered, reverse=True), point["month"]

        tracked = [p["sites_tracked"] for p in points]
        assert tracked == sorted(tracked), "cumulative site count must never fall"

    def test_growth_months_are_ordered_and_well_formed(self, api_client: TestClient) -> None:
        payload = api_client.get("/analytics/growth").json()
        months = [p["month"] for p in payload["points"]]
        assert months == sorted(months)
        for month in months:
            year, sep, mon = month.partition("-")
            assert sep == "-" and len(year) == 4 and len(mon) == 2

    def test_detection_lag_is_reported_not_clamped(self, api_client: TestClient) -> None:
        """Negative lag is a real outcome and must survive to the response.

        Clamping at zero would quietly flatter an early-warning claim that this
        endpoint exists to test rather than assert.
        """
        payload = api_client.get("/analytics/detection-lag").json()
        assert payload["transitions"] > 0

        assert payload["min_lag_days"] <= payload["max_lag_days"]
        assert payload["median_lag_days"] is not None
        assert payload["p90_lag_days"] >= payload["median_lag_days"]

        for entry in payload["slowest"]:
            assert entry["project_code"]
            assert entry["stage_label"]
            # The arithmetic must be reproducible from the fields shown.
            assert isinstance(entry["lag_days"], int)

    def test_detection_lag_slowest_is_ordered_worst_first(self, api_client: TestClient) -> None:
        payload = api_client.get("/analytics/detection-lag").json()
        lags = [e["lag_days"] for e in payload["slowest"]]
        assert lags == sorted(lags, reverse=True)


class TestAreaConsumption:
    def test_returns_the_regions_reported_totals(self, api_client: TestClient) -> None:
        payload = api_client.get("/analytics/area-consumption").json()
        assert payload["region_slug"] == "east-valley-az"

        metrics = {t["metric"] for t in payload["totals"]}
        assert "public_supply_water_withdrawal" in metrics
        assert "electricity_retail_sales" in metrics

    def test_every_area_total_is_reported(self, api_client: TestClient) -> None:
        """These are the one set of figures on the site Helios did not derive.

        If any of them ever came back as anything but reported, the whole point
        of having a measured denominator would be gone.
        """
        payload = api_client.get("/analytics/area-consumption").json()
        assert payload["totals"]
        for total in payload["totals"]:
            assert total["assertion_class"] == "reported", total["metric"]
            assert total["source_slug"]
            assert total["reference_year"] > 1990

    def test_totals_are_scoped_to_the_regions_counties_and_state(
        self, api_client: TestClient
    ) -> None:
        payload = api_client.get("/analytics/area-consumption").json()
        for total in payload["totals"]:
            if total["area_kind"] == "county":
                assert total["area_code"] in {"04013", "04021"}
            else:
                assert total["area_kind"] == "state"
                assert total["area_code"] == "AZ"

    def test_water_and_electricity_do_not_pretend_to_share_a_geography(
        self, api_client: TestClient
    ) -> None:
        """Water is county-level and electricity state-level. A reader must be
        able to see that from the response rather than having to know it."""
        payload = api_client.get("/analytics/area-consumption").json()
        by_metric = {t["metric"]: t["area_kind"] for t in payload["totals"]}
        assert by_metric["public_supply_water_withdrawal"] == "county"
        assert by_metric["electricity_retail_sales"] == "state"
        assert payload["granularity_note"]

    def test_maricopa_public_supply_matches_the_published_figure(
        self, api_client: TestClient
    ) -> None:
        payload = api_client.get("/analytics/area-consumption").json()
        maricopa = [
            t
            for t in payload["totals"]
            if t["area_code"] == "04013" and t["metric"] == "public_supply_water_withdrawal"
        ]
        assert len(maricopa) == 1
        assert maricopa[0]["value"] == pytest.approx(776.54)
        assert maricopa[0]["unit"] == "Mgal/d"

    def test_comparisons_state_their_bounds_and_their_caveat(self, api_client: TestClient) -> None:
        """A ratio of an inference to a measurement must not render as a fact."""
        payload = api_client.get("/analytics/area-consumption").json()
        assert payload["comparisons"], "sites with estimates should produce comparisons"

        for comparison in payload["comparisons"]:
            assert comparison["inferred_lower"] <= comparison["inferred_likely"]
            assert comparison["inferred_likely"] <= comparison["inferred_upper"]
            assert comparison["share_lower_pct"] <= comparison["share_likely_pct"]
            assert comparison["share_likely_pct"] <= comparison["share_upper_pct"]
            assert comparison["caveat"]
            assert comparison["assumptions"]
            assert comparison["method"]

    def test_comparisons_are_never_labelled_reported(self, api_client: TestClient) -> None:
        """The reported totals and the inferred comparisons stay in separate
        lists precisely so nothing can read one as the other."""
        payload = api_client.get("/analytics/area-consumption").json()
        for comparison in payload["comparisons"]:
            assert "assertion_class" not in comparison

    def test_water_comparison_converts_gallons_to_millions(self, api_client: TestClient) -> None:
        """Site estimates are GPD and county totals Mgal/d. Comparing them
        unconverted would be wrong by a factor of a million."""
        payload = api_client.get("/analytics/area-consumption").json()
        water = [
            c for c in payload["comparisons"] if c["metric"] == "public_supply_water_withdrawal"
        ]
        assert len(water) == 1
        assert water[0]["unit"] == "Mgal/d"
        # A handful of inferred sites cannot plausibly rival a metro's entire
        # municipal supply; a unit error would put this in the thousands.
        assert water[0]["share_likely_pct"] < 100

    def test_electricity_comparison_is_annualised_energy_not_capacity(
        self, api_client: TestClient
    ) -> None:
        payload = api_client.get("/analytics/area-consumption").json()
        power = [c for c in payload["comparisons"] if c["metric"] == "electricity_retail_sales"]
        assert len(power) == 1
        assert power[0]["unit"] == "MWh/yr"
        # The load factor must be published, not buried in the arithmetic.
        assert "load_factor_likely" in power[0]["assumptions"]
        assert power[0]["assumptions"]["hours_per_year"] == 8760

    def test_the_same_request_twice_returns_identical_bytes(self, api_client: TestClient) -> None:
        """Float addition is not associative and Postgres promises no row order,
        so an unrounded sum over the same 13 sites can differ in its last bit
        between two identical requests. That drift reached the published static
        export once; a figure that changes when nothing changed is a defect in a
        project whose claim is that its numbers can be re-derived."""
        first = api_client.get("/analytics/area-consumption").text
        second = api_client.get("/analytics/area-consumption").text
        assert first == second

    def test_summed_estimates_keep_the_precision_of_their_inputs(
        self, api_client: TestClient
    ) -> None:
        """Inputs are produced rounded to one decimal, so a sum of them carries
        no more precision than that and must not pretend to."""
        payload = api_client.get("/analytics/area-consumption").json()
        power = next(c for c in payload["comparisons"] if c["metric"] == "electricity_retail_sales")
        for key in ("power_mw_lower", "power_mw_likely", "power_mw_upper"):
            value = power["assumptions"][key]
            assert round(value, 1) == value, f"{key} carries false precision: {value!r}"

    def test_unknown_region_is_a_404_not_an_empty_success(self, api_client: TestClient) -> None:
        response = api_client.get("/analytics/area-consumption", params={"region": "atlantis"})
        assert response.status_code == 404

    def test_declared_region_returns_no_totals_rather_than_borrowed_ones(
        self, api_client: TestClient
    ) -> None:
        """A declared region holds no data. It must come back empty, not with
        another region's figures standing in."""
        response = api_client.get(
            "/analytics/area-consumption", params={"region": "northern-virginia"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["totals"] == []
        assert payload["comparisons"] == []


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

    def test_evidence_bundle_is_verifiable(self, api_client: TestClient, site_id: str) -> None:
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


class TestGenerationCapacity:
    def test_capacity_totals_are_published_with_their_own_year(
        self, api_client: TestClient
    ) -> None:
        """EIA's sales file stops at 2020 and its capacity file runs to 2024.
        Each figure carries the year it describes rather than being aligned to
        the other, because matching another dataset's staleness is worse."""
        payload = api_client.get("/analytics/area-consumption").json()
        by_metric = {t["metric"]: t for t in payload["totals"]}

        capacity = by_metric["generation_summer_capacity"]
        sales = by_metric["electricity_retail_sales"]
        assert capacity["reference_year"] > sales["reference_year"]
        assert capacity["unit"] == "MW"

    def test_summer_capacity_is_below_nameplate(self, api_client: TestClient) -> None:
        payload = api_client.get("/analytics/area-consumption").json()
        by_metric = {t["metric"]: t["value"] for t in payload["totals"]}
        assert by_metric["generation_summer_capacity"] < by_metric["generation_nameplate_capacity"]

    def test_capacity_comparison_needs_no_unit_conversion(self, api_client: TestClient) -> None:
        """Both sides are a peak figure in MW, so unlike the water and annual
        energy comparisons this one carries no conversion assumption at all."""
        payload = api_client.get("/analytics/area-consumption").json()
        headroom = next(
            c for c in payload["comparisons"] if c["metric"] == "generation_summer_capacity"
        )
        assert headroom["unit"] == "MW"
        assert "load_factor_likely" not in headroom["assumptions"]
        assert "gallons_per_million" not in headroom["assumptions"]

    def test_capacity_comparison_refuses_to_imply_spare_room(self, api_client: TestClient) -> None:
        """A share of total capacity is not a share of unused capacity. Existing
        demand already consumes most of that figure and Helios does not know how
        much, so the response must say so rather than let the percentage imply
        headroom it has not measured."""
        payload = api_client.get("/analytics/area-consumption").json()
        headroom = next(
            c for c in payload["comparisons"] if c["metric"] == "generation_summer_capacity"
        )
        assert "not spare capacity" in headroom["caveat"]
        assert "interconnection" in headroom["caveat"]

    def test_capacity_share_is_bounded_and_ordered(self, api_client: TestClient) -> None:
        payload = api_client.get("/analytics/area-consumption").json()
        headroom = next(
            c for c in payload["comparisons"] if c["metric"] == "generation_summer_capacity"
        )
        assert 0 < headroom["share_likely_pct"] < 100
        assert headroom["share_lower_pct"] <= headroom["share_likely_pct"]
        assert headroom["share_likely_pct"] <= headroom["share_upper_pct"]
