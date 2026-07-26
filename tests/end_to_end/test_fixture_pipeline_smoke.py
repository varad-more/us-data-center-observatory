"""End-to-end smoke: fixture ingest → sites → score → API-shaped reads.

Requires PostgreSQL/PostGIS via ``HELIOS_TEST_DATABASE_URL``. Skips otherwise.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_connectors.azcc_edocket import AzccEdocketConnector, default_fixture_dir
from helios_connectors.epa_echo import EpaEchoAirConnector
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.sync import sync_registry
from helios_domain.models import Site
from helios_geospatial.site_builder import build_sites
from helios_scoring.service import recalculate_site
from tests.integration.test_ingestion_pipeline import _replay

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

EAST_VALLEY = ("Mesa", "Chandler", "Tempe", "Gilbert", "Queen Creek", "Apache Junction")


def test_fixture_pipeline_produces_scored_sites(db_session, settings) -> None:
    sync_registry(db_session)
    store = FilesystemEvidenceStore(settings.evidence_root)

    assessor = _replay(
        MaricopaAssessorConnector,
        ("maricopa_assessor", "east_valley_data_centers.json"),
        "parcel-query:e2e",
    )
    osm = _replay(
        OsmPowerConnector,
        ("osm_power", "east_valley_power.json"),
        "overpass:power:e2e",
    )
    echo = _replay(
        EpaEchoAirConnector,
        ("epa_echo", "mesa_air_facilities.json"),
        "echo:air:e2e",
        cities=("Mesa", "Chandler"),
    )
    azcc = AzccEdocketConnector(fixture_root=default_fixture_dir())

    for connector in (assessor, osm, echo, azcc):
        summary = IngestionPipeline(db_session, connector, store, mode="fixture").run()
        assert summary.status == "success", summary.errors

    built = build_sites(db_session, region_cities=EAST_VALLEY)
    assert built.sites_created >= 1

    sites = list(db_session.scalars(select(Site)).all())
    assert sites
    for site in sites:
        outcome = recalculate_site(db_session, site)
        assert 0.0 <= outcome.score.confidence <= 100.0

    mesa = db_session.scalar(select(Site).where(Site.project_code == "AZ-MESA-001"))
    # Project codes are minted in creation order; locate the Signal Butte campus
    # by summary text if the code differs.
    flagship = mesa or next(
        (s for s in sites if s.summary and "SIGNAL BUTTE" in s.summary.upper()),
        sites[0],
    )
    assert flagship.evidence_count >= 1
    assert flagship.current_stage >= 0
