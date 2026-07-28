"""Integration tests for the ingestion pipeline against PostgreSQL and PostGIS.

The central property under test is **idempotency**: running a connector twice
over unchanged source content must leave the database in the same state, adding
no duplicate documents, versions, or evidence. Everything else in Helios depends
on this, because connectors are expected to run nightly against sources that
mostly do not change.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_connectors.base import BaseConnector
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.replay import replay_connector as _replay
from helios_domain.models import (
    ConnectorRun,
    DocumentVersion,
    EvidenceRecord,
    IngestionFailure,
    Organization,
    Parcel,
    ParcelOwnershipEvent,
    Source,
    SourceDocument,
    Substation,
    TransmissionLine,
)
from tests.conftest import load_fixture_bytes

pytestmark = [pytest.mark.integration]


@pytest.fixture
def assessor_connector() -> BaseConnector:
    return _replay(
        MaricopaAssessorConnector,
        ("maricopa_assessor", "east_valley_data_centers.json"),
        "parcel-query:test:offset:0",
    )


@pytest.fixture
def osm_connector() -> BaseConnector:
    return _replay(
        OsmPowerConnector,
        ("osm_power", "east_valley_power.json"),
        "overpass:power:east-valley",
    )


@pytest.fixture
def store(settings) -> FilesystemEvidenceStore:
    return FilesystemEvidenceStore(settings.evidence_root)


class TestRegistrySync:
    def test_projects_every_declared_source(self, registered_sources: Session) -> None:
        from helios_connectors.registry import SOURCE_REGISTRY

        count = registered_sources.scalar(select(func.count()).select_from(Source))
        assert count == len(SOURCE_REGISTRY)

    def test_is_idempotent(self, registered_sources: Session) -> None:
        from helios_connectors.registry import SOURCE_REGISTRY
        from helios_connectors.sync import sync_registry

        sync_registry(registered_sources)
        sync_registry(registered_sources)
        count = registered_sources.scalar(select(func.count()).select_from(Source))
        assert count == len(SOURCE_REGISTRY)

    def test_records_access_limitations_for_blocked_sources(
        self, registered_sources: Session
    ) -> None:
        """A blocked source must remain visible, with the reason recorded."""
        from helios_domain.models import SourceConnector

        edocket = registered_sources.scalar(
            select(SourceConnector).where(SourceConnector.slug == "azcc-edocket")
        )
        assert edocket is not None
        assert edocket.status == "fixture_only"
        assert edocket.access_limitation
        assert "no documented API" in edocket.access_limitation


class TestParcelIngestion:
    def test_ingests_real_parcels_with_geometry(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        pipeline = IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture")
        summary = pipeline.run()

        assert summary.status == "success"
        assert summary.items_normalized == 14
        assert summary.versions_created == 1

        parcels = registered_sources.scalars(select(Parcel)).all()
        assert len(parcels) == 14
        assert all(p.geometry is not None for p in parcels)

    def test_county_survives_the_flush_inside_owner_resolution(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        """Resolving a parcel's owner can create an organization, and that flushes.

        The parcel is added to the session before that happens, so every
        non-nullable column must already be set or the half-built row reaches the
        database. This passed for a long time only because ``county`` carried a
        ``"Maricopa"`` default that filled the hole -- a default that would have
        mislabelled any parcel loaded from another county.
        """
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        counties = {p.county for p in registered_sources.scalars(select(Parcel)).all()}
        assert counties == {"Maricopa"}

    def test_stores_payload_immutably_and_verifiably(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        version = registered_sources.scalars(select(DocumentVersion)).one()
        assert store.exists(version.storage_key)
        assert store.verify(version.storage_key, version.content_sha256)
        assert version.version_number == 1
        assert version.content_length > 0

    def test_creates_distinct_evidence_per_assertion(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        """Each of the 14 parcels asserts a current classification; some also
        assert a past transfer and single-purpose-entity ownership."""
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        by_kind: dict[str, int] = {}
        for record in registered_sources.scalars(select(EvidenceRecord)).all():
            by_kind[record.evidence_kind] = by_kind.get(record.evidence_kind, 0) + 1

        assert by_kind["assessor_data_center_classification"] == 14
        assert by_kind["large_industrial_parcel_acquisition"] >= 1
        assert by_kind["shell_entity_ownership"] >= 1

    def test_standing_conditions_are_dated_to_observation_not_the_deed(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        """A current-use classification must not inherit a decade-old deed date."""
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        parcel = registered_sources.scalar(select(Parcel).where(Parcel.apn == "30433005S"))
        assert parcel is not None
        records = {
            r.evidence_kind: r
            for r in registered_sources.scalars(
                select(EvidenceRecord).where(EvidenceRecord.parcel_id == parcel.id)
            ).all()
        }
        classification = records["assessor_data_center_classification"]
        acquisition = records["large_industrial_parcel_acquisition"]

        assert acquisition.observed_at.isoformat() == "2013-11-04"
        assert classification.observed_at > acquisition.observed_at
        assert classification.normalized_values["is_standing_condition"] is True

    def test_every_evidence_record_has_complete_provenance(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        """Provenance completeness is a headline metric; it must be 100%."""
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        for evidence in registered_sources.scalars(select(EvidenceRecord)).all():
            assert evidence.document_id is not None
            assert evidence.document_version_id is not None
            assert evidence.snippet
            assert evidence.snippet_locator
            assert evidence.observed_at is not None
            assert evidence.parser_version
            assert 0.0 <= evidence.confidence <= 1.0

    def test_creates_organizations_for_corporate_owners(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        platypus = registered_sources.scalar(
            select(Organization).where(Organization.canonical_name == "PLATYPUS DEVELOPMENT LLC")
        )
        assert platypus is not None
        assert platypus.is_suspected_shell is True
        assert platypus.organization_type == "LLC"
        assert platypus.is_natural_person is False

    def test_records_deed_as_ownership_event_with_recorder_link(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        parcel = registered_sources.scalar(select(Parcel).where(Parcel.apn == "30433005S"))
        assert parcel is not None
        event = registered_sources.scalar(
            select(ParcelOwnershipEvent).where(ParcelOwnershipEvent.parcel_id == parcel.id)
        )
        assert event is not None
        assert event.event_date.isoformat() == "2013-11-04"
        assert event.deed_number == "20130962087"
        assert "recorder.maricopa.gov" in event.deed_url

    def test_preserves_alpha_suffixed_apn(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()
        assert registered_sources.scalar(select(Parcel).where(Parcel.apn == "30433005S"))


class TestIdempotency:
    """Re-running an unchanged source must be a no-op for the evidence graph."""

    def test_second_identical_run_creates_no_new_version(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        for _ in range(2):
            connector = _replay(
                MaricopaAssessorConnector,
                ("maricopa_assessor", "east_valley_data_centers.json"),
                "parcel-query:test:offset:0",
            )
            IngestionPipeline(registered_sources, connector, store, mode="fixture").run()

        assert registered_sources.scalar(select(func.count()).select_from(SourceDocument)) == 1
        assert registered_sources.scalar(select(func.count()).select_from(DocumentVersion)) == 1

    def test_second_identical_run_creates_no_duplicate_evidence(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        """Duplicate evidence would inflate confidence scores without new information."""
        counts = []
        for _ in range(2):
            connector = _replay(
                MaricopaAssessorConnector,
                ("maricopa_assessor", "east_valley_data_centers.json"),
                "parcel-query:test:offset:0",
            )
            IngestionPipeline(registered_sources, connector, store, mode="fixture").run()
            counts.append(
                registered_sources.scalar(select(func.count()).select_from(EvidenceRecord))
            )

        assert counts[0] == counts[1]
        assert counts[0] > 0

    def test_second_identical_run_creates_no_duplicate_parcels(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        for _ in range(2):
            connector = _replay(
                MaricopaAssessorConnector,
                ("maricopa_assessor", "east_valley_data_centers.json"),
                "parcel-query:test:offset:0",
            )
            IngestionPipeline(registered_sources, connector, store, mode="fixture").run()

        assert registered_sources.scalar(select(func.count()).select_from(Parcel)) == 14
        assert (
            registered_sources.scalar(select(func.count()).select_from(ParcelOwnershipEvent)) == 14
        )

    def test_second_run_is_reported_as_unchanged(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        summaries = []
        for _ in range(2):
            connector = _replay(
                MaricopaAssessorConnector,
                ("maricopa_assessor", "east_valley_data_centers.json"),
                "parcel-query:test:offset:0",
            )
            summaries.append(
                IngestionPipeline(registered_sources, connector, store, mode="fixture").run()
            )

        assert summaries[0].versions_created == 1
        assert summaries[1].versions_created == 0
        assert summaries[1].items_unchanged == 1
        assert summaries[1].evidence_created == 0

    def test_changed_content_creates_a_second_version(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        """A genuinely edited source record must be preserved as a new version."""
        original = load_fixture_bytes("maricopa_assessor", "east_valley_data_centers.json")
        amended = original.replace(b'"LotSize_Acre":83.171459999999996', b'"LotSize_Acre":91.5')
        assert amended != original

        for payload in (original, amended):
            connector = _replay(
                MaricopaAssessorConnector,
                ("maricopa_assessor", "east_valley_data_centers.json"),
                "parcel-query:test:offset:0",
                payload=payload,
            )
            IngestionPipeline(registered_sources, connector, store, mode="fixture").run()

        versions = registered_sources.scalars(
            select(DocumentVersion).order_by(DocumentVersion.version_number)
        ).all()
        assert len(versions) == 2
        assert versions[1].supersedes_version_id == versions[0].id

        document = registered_sources.scalars(select(SourceDocument)).one()
        assert document.version_count == 2
        # The superseded payload remains retrievable, which is what makes
        # "what did this record say in July?" answerable.
        assert store.verify(versions[0].storage_key, versions[0].content_sha256)


class TestPowerInfrastructureIngestion:
    def test_ingests_substations_and_lines(
        self,
        registered_sources: Session,
        osm_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        summary = IngestionPipeline(registered_sources, osm_connector, store, mode="fixture").run()
        assert summary.status == "success"

        substations = registered_sources.scalars(select(Substation)).all()
        lines = registered_sources.scalars(select(TransmissionLine)).all()
        assert len(substations) == 175
        assert len(lines) > 0

    def test_stores_multi_voltage_substation_correctly(
        self,
        registered_sources: Session,
        osm_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, osm_connector, store, mode="fixture").run()

        greenbone = registered_sources.scalar(
            select(Substation).where(Substation.name == "Greenbone Substation")
        )
        assert greenbone is not None
        assert greenbone.max_voltage_kv == 500.0
        assert greenbone.operator_name == "Salt River Project"
        assert greenbone.location is not None


class TestRunTelemetry:
    def test_records_a_run_row_with_counts(
        self,
        registered_sources: Session,
        assessor_connector: BaseConnector,
        store: FilesystemEvidenceStore,
    ) -> None:
        IngestionPipeline(registered_sources, assessor_connector, store, mode="fixture").run()

        run = registered_sources.scalars(select(ConnectorRun)).one()
        assert run.status == "success"
        assert run.finished_at is not None
        assert run.duration_seconds is not None
        assert run.items_normalized == 14
        assert run.mode == "fixture"

    def test_records_dead_letter_rows_for_bad_records(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        """One malformed page must not abort the run, but must be countable."""
        connector = _replay(
            MaricopaAssessorConnector,
            ("maricopa_assessor", "east_valley_data_centers.json"),
            "parcel-query:broken:offset:0",
            payload=b'{"error": {"code": 400, "message": "Failed to execute query."}}',
        )
        summary = IngestionPipeline(registered_sources, connector, store, mode="fixture").run()

        assert summary.status == "success"
        assert summary.items_parsed == 0
        failures = registered_sources.scalars(select(IngestionFailure)).all()
        assert len(failures) == 1
        assert failures[0].stage == "parse"

    def test_detects_upstream_schema_drift(
        self,
        registered_sources: Session,
        store: FilesystemEvidenceStore,
    ) -> None:
        """A renamed upstream column must raise an alert, not produce silent nulls."""
        original = load_fixture_bytes("maricopa_assessor", "east_valley_data_centers.json")
        renamed = original.replace(b'"LotSize_Acre"', b'"LotSizeAcres"')

        first = _replay(
            MaricopaAssessorConnector,
            ("maricopa_assessor", "east_valley_data_centers.json"),
            "parcel-query:drift:offset:0",
            payload=original,
        )
        IngestionPipeline(registered_sources, first, store, mode="fixture").run()

        second = _replay(
            MaricopaAssessorConnector,
            ("maricopa_assessor", "east_valley_data_centers.json"),
            "parcel-query:drift:offset:0",
            payload=renamed,
        )
        summary = IngestionPipeline(registered_sources, second, store, mode="fixture").run()

        assert summary.schema_drift_detected is True
        drift_failures = registered_sources.scalars(
            select(IngestionFailure).where(IngestionFailure.error_category == "schema_drift")
        ).all()
        assert len(drift_failures) == 1

    def test_refuses_to_ingest_for_an_unregistered_source(
        self, db_session: Session, assessor_connector: BaseConnector, store: FilesystemEvidenceStore
    ) -> None:
        """Ingesting from an undeclared source would bypass the licensing review.

        This raises rather than returning a failed summary because a run row
        cannot exist without a connector row, which cannot exist without a
        source: there is nowhere to record the failure. It is a configuration
        error, not a data error, and should stop the caller.
        """
        with pytest.raises(LookupError, match="not registered"):
            IngestionPipeline(db_session, assessor_connector, store, mode="fixture").run()
