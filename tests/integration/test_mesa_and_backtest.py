"""Integration: Mesa address matching + historical backtest harness."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_connectors.base import BaseConnector
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.mesa_permits import MesaBuildingPermitsConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.replay import replay_connector as _replay
from helios_domain.models import EvidenceRecord, Permit, Site
from helios_domain.ontology import StageEvidenceKind
from helios_geospatial.site_builder import build_sites
from helios_scoring.backtest import DEFAULT_CASES_PATH, run_backtest

pytestmark = [pytest.mark.integration]


def _labelled_case_count() -> int:
    """Number of labelled cases in the default backtest corpus."""
    import json

    payload = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8"))
    return len(payload["cases"] if isinstance(payload, dict) else payload)


@pytest.fixture
def store(settings) -> FilesystemEvidenceStore:
    return FilesystemEvidenceStore(settings.evidence_root)


@pytest.fixture
def assessor_connector() -> BaseConnector:
    return _replay(
        MaricopaAssessorConnector,
        ("maricopa_assessor", "east_valley_data_centers.json"),
        "parcel-query:mesa-test",
    )


@pytest.fixture
def mesa_connector() -> BaseConnector:
    return _replay(
        MesaBuildingPermitsConnector,
        ("mesa_permits", "east_valley_com.json"),
        "mesa-permits:test",
        street_filters=("SIGNAL BUTTE", "ELLSWORTH", "HOLMES", "EVERTON"),
    )


class TestMesaAddressMatching:
    def test_matches_signal_butte_permits_onto_parcel_and_site(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        mesa_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()
        summary = IngestionPipeline(registered_sources, mesa_connector, store, mode="fixture").run()
        assert summary.status == "success"

        matched = registered_sources.scalars(
            select(Permit).where(Permit.parcel_id.is_not(None))
        ).all()
        assert matched, "Expected at least one Mesa permit to match a parcel by address"
        assert any(
            (p.attributes or {}).get("address_match", {}).get("normalized")
            == "3740 S SIGNAL BUTTE RD"
            for p in matched
        )

        build_sites(registered_sources)
        construction = registered_sources.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.evidence_kind
                == str(StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT),
                EvidenceRecord.site_id.is_not(None),
            )
        ).all()
        assert construction


class TestBacktestHarness:
    def test_east_valley_cases_pass_on_fixture_pipeline(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()
        build_sites(registered_sources)
        # Score live once so AZ-MESA-001 has a current stage, then backtest.
        from helios_scoring.service import recalculate_site

        for site in registered_sources.scalars(select(Site)).all():
            recalculate_site(registered_sources, site)

        report = run_backtest(registered_sources)
        # Derived from the corpus rather than hard-coded, so growing the labelled
        # case set does not silently leave this assertion behind.
        assert report.total == _labelled_case_count()
        assert report.passed == report.total, report.as_dict()
        # Live stage must remain untouched by historical replay.
        mesa = registered_sources.scalar(select(Site).where(Site.project_code == "AZ-MESA-001"))
        assert mesa is not None
        assert mesa.current_stage == 7
