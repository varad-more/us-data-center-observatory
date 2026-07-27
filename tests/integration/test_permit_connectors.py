"""Integration tests for permit loaders (EPA ECHO + ACC eDocket fixtures)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_connectors.azcc_edocket import AzccEdocketConnector, default_fixture_dir
from helios_connectors.base import BaseConnector
from helios_connectors.epa_echo import EpaEchoAirConnector
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.replay import replay_connector as _replay
from helios_domain.models import EvidenceRecord, Permit
from helios_domain.ontology import StageEvidenceKind
from helios_geospatial.site_builder import build_sites

pytestmark = [pytest.mark.integration]

EAST_VALLEY = ("Mesa", "Chandler", "Tempe", "Gilbert", "Queen Creek", "Apache Junction")


@pytest.fixture
def store(settings) -> FilesystemEvidenceStore:
    return FilesystemEvidenceStore(settings.evidence_root)


@pytest.fixture
def echo_connector() -> BaseConnector:
    return _replay(
        EpaEchoAirConnector,
        ("epa_echo", "mesa_air_facilities.json"),
        "echo:air:test",
        cities=("Mesa", "Chandler"),
    )


@pytest.fixture
def assessor_connector() -> BaseConnector:
    return _replay(
        MaricopaAssessorConnector,
        ("maricopa_assessor", "east_valley_data_centers.json"),
        "parcel-query:test:offset:0",
    )


class TestPermitIngestion:
    def test_echo_creates_permits_and_generator_evidence(
        self,
        registered_sources: Session,
        echo_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        summary = IngestionPipeline(registered_sources, echo_connector, store, mode="fixture").run()
        assert summary.status == "success"
        assert summary.items_filtered == 2
        permit_count = registered_sources.scalar(select(func.count()).select_from(Permit))
        assert permit_count == 2
        kinds = set(registered_sources.scalars(select(EvidenceRecord.evidence_kind)).all())
        assert str(StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT) in kinds

    def test_azcc_fixture_connector_ingests_filings(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        connector = AzccEdocketConnector(fixture_root=default_fixture_dir())
        summary = IngestionPipeline(registered_sources, connector, store, mode="fixture").run()
        assert summary.status == "success"
        assert summary.items_discovered >= 2
        kinds = set(registered_sources.scalars(select(EvidenceRecord.evidence_kind)).all())
        assert str(StageEvidenceKind.SUBSTATION_APPLICATION) in kinds
        assert str(StageEvidenceKind.TRANSMISSION_FILING) in kinds

    def test_site_builder_attaches_nearby_echo_evidence(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        echo_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()
        IngestionPipeline(registered_sources, echo_connector, store, mode="fixture").run()
        result = build_sites(registered_sources, region_cities=EAST_VALLEY)
        assert result.sites_created >= 1

        attached = registered_sources.scalars(
            select(EvidenceRecord).where(
                EvidenceRecord.evidence_kind == str(StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT),
                EvidenceRecord.site_id.is_not(None),
            )
        ).all()
        assert attached, "Expected ECHO generator evidence to attach to a nearby site"
