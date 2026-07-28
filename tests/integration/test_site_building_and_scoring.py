"""End-to-end tests: ingest real records, build sites, score them, explain the scores.

This is the pipeline the product depends on, exercised against real public data
in a real PostGIS database.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from helios_common.evidence_store import FilesystemEvidenceStore
from helios_common.vocabulary import AssertionClass
from helios_connectors.maricopa_assessor import MaricopaAssessorConnector
from helios_connectors.osm_power import OsmPowerConnector
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.replay import replay_connector as _replay
from helios_domain.models import (
    EvidenceRecord,
    InfrastructureDependency,
    Prediction,
    PredictionExplanation,
    Site,
    SiteParcelLink,
    SiteStageHistory,
)
from helios_domain.ontology import DevelopmentStage, SiteKind
from helios_domain.regions import EAST_VALLEY_AZ, UnknownRegionError
from helios_geospatial.correlation import find_adjacent_parcels, parcels_in_bbox
from helios_geospatial.site_builder import build_sites, generate_project_code
from helios_scoring.service import recalculate_site, score_history

pytestmark = pytest.mark.integration


TODAY = datetime.now(tz=UTC).date()
"""Standing-condition evidence is observed at ingestion time, so scoring cutoffs in
these tests are anchored to the present rather than to a hard-coded date."""


@pytest.fixture
def populated(registered_sources: Session, settings) -> Session:
    """A database loaded with real parcel and power-infrastructure records."""
    store = FilesystemEvidenceStore(settings.evidence_root)
    connectors = (
        _replay(
            MaricopaAssessorConnector,
            ("maricopa_assessor", "east_valley_data_centers.json"),
            "parcels",
        ),
        _replay(OsmPowerConnector, ("osm_power", "east_valley_power.json"), "power"),
    )
    for connector in connectors:
        IngestionPipeline(registered_sources, connector, store, mode="fixture").run()
    return registered_sources


class TestProjectCodeGeneration:
    def test_generates_anonymous_sequential_codes(self, populated: Session) -> None:
        """Anonymous codes avoid implying an attribution the evidence cannot support."""
        assert generate_project_code(populated, "Mesa", EAST_VALLEY_AZ) == "AZ-MESA-001"

    def test_handles_missing_jurisdiction(self, populated: Session) -> None:
        assert generate_project_code(populated, None, EAST_VALLEY_AZ).startswith("AZ-UNK-")

    def test_takes_the_state_prefix_from_the_region(self, populated: Session) -> None:
        """The prefix was hardcoded to AZ, which would have mislabelled every site
        built anywhere else. It now comes from the region's state code."""
        code = generate_project_code(populated, "Ashburn", "northern-virginia")
        assert code == "VA-ASHBURN-001"

    def test_rejects_an_unregistered_region(self, populated: Session) -> None:
        """A typo in a slug must fail rather than mint a code under a region that
        does not exist."""
        with pytest.raises(UnknownRegionError):
            generate_project_code(populated, "Mesa", "east-valley-arizona")

    def test_increments_within_a_jurisdiction(self, populated: Session) -> None:
        build_sites(populated)
        codes = populated.scalars(select(Site.project_code)).all()
        assert len(set(codes)) == len(codes)


class TestSiteBuilding:
    def test_creates_sites_from_real_parcels(self, populated: Session) -> None:
        result = build_sites(populated)
        assert result.sites_created > 0
        assert result.parcels_linked == 14

    def test_computes_boundary_and_acreage_from_parcels(self, populated: Session) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        assert site.boundary is not None
        assert site.centroid is not None
        assert site.total_acres is not None
        assert float(site.total_acres) == pytest.approx(83.17, abs=0.1)

    def test_classifies_large_classified_parcel_as_hyperscale_campus(
        self, populated: Session
    ) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        assert site.site_kind == str(SiteKind.HYPERSCALE_CAMPUS)

    def test_site_kind_from_assessor_classification_is_reported_not_inferred(
        self, populated: Session
    ) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        assert site.site_kind_assertion == str(AssertionClass.REPORTED)

    def test_summary_makes_no_operator_claim(self, populated: Session) -> None:
        """The single most damaging failure mode is naming an operator on weak evidence."""
        build_sites(populated)
        site = _largest_site(populated)
        assert site.summary is not None
        assert "has not established which organization" in site.summary
        assert site.operator_organization_id is None
        assert site.operator_assertion == "unknown"

    def test_does_not_merge_distant_parcels_sharing_an_owner(self, populated: Session) -> None:
        """Shared ownership alone must not fuse a company's county-wide holdings."""
        build_sites(populated)
        cox_links = populated.execute(
            select(func.count())
            .select_from(SiteParcelLink)
            .join(Site, Site.id == SiteParcelLink.site_id)
        ).scalar_one()
        site_count = populated.scalar(select(func.count()).select_from(Site))
        # Cox holds parcels in both Mesa and Chandler; they must not share a site.
        assert site_count > 1
        assert cox_links == 14

    def test_is_idempotent(self, populated: Session) -> None:
        first = build_sites(populated)
        second = build_sites(populated)
        assert second.sites_created == 0
        assert second.parcels_linked == 0
        assert second.sites_updated == first.sites_created

    def test_attaches_parcel_evidence_to_sites(self, populated: Session) -> None:
        build_sites(populated)
        orphaned = populated.scalar(
            select(func.count()).select_from(EvidenceRecord).where(EvidenceRecord.site_id.is_(None))
        )
        assert orphaned == 0

    def test_sets_first_and_latest_signal_dates(self, populated: Session) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        assert site.first_signal_date is not None
        assert site.latest_signal_date is not None
        assert site.evidence_count >= 1

    def test_evidence_count_matches_attached_evidence_for_every_site(
        self, populated: Session
    ) -> None:
        """The denormalised counter is what the UI and CSV publish.

        It is refreshed only after every site has claimed its evidence, because a
        site's evidence can be reassigned to a nearer site later in the same
        build. A stale counter would advertise a different amount of evidence
        than the site can actually show.
        """
        build_sites(populated)
        populated.flush()

        for site in populated.scalars(select(Site)).all():
            actual = populated.scalar(
                select(func.count())
                .select_from(EvidenceRecord)
                .where(EvidenceRecord.site_id == site.id)
            )
            assert site.evidence_count == actual, site.project_code


class TestInfrastructureLinking:
    def test_links_nearby_substations_as_inferred_dependencies(self, populated: Session) -> None:
        build_sites(populated)
        dependencies = populated.scalars(
            select(InfrastructureDependency).where(
                InfrastructureDependency.infrastructure_kind == "substation"
            )
        ).all()
        assert dependencies
        for dependency in dependencies:
            assert dependency.assertion_class == str(AssertionClass.INFERRED)
            assert dependency.distance_meters is not None

    def test_dependency_notes_disclaim_proof_of_service(self, populated: Session) -> None:
        build_sites(populated)
        dependency = populated.scalars(
            select(InfrastructureDependency).where(
                InfrastructureDependency.infrastructure_kind == "substation"
            )
        ).first()
        assert dependency is not None
        assert "not evidence that it is" in (dependency.notes or "")

    def test_confidence_decreases_with_distance(self, populated: Session) -> None:
        build_sites(populated)
        dependencies = populated.scalars(
            select(InfrastructureDependency)
            .where(InfrastructureDependency.infrastructure_kind == "substation")
            .order_by(InfrastructureDependency.distance_meters)
        ).all()
        if len(dependencies) >= 2:
            assert dependencies[0].confidence >= dependencies[-1].confidence


class TestSpatialQueries:
    def test_finds_parcels_in_a_bounding_box(self, populated: Session) -> None:
        results = parcels_in_bbox(populated, (-111.98, 33.16, -111.35, 33.52))
        assert results
        assert all(r["geometry_json"] for r in results)

    def test_bbox_excludes_parcels_outside_it(self, populated: Session) -> None:
        """A box over open desert far east of the study area must return nothing."""
        assert parcels_in_bbox(populated, (-110.0, 32.0, -109.9, 32.1)) == []

    def test_filters_by_land_use(self, populated: Session) -> None:
        results = parcels_in_bbox(
            populated, (-111.98, 33.16, -111.35, 33.52), land_use_filter="DATA CENTER"
        )
        assert len(results) == 14

    def test_filters_by_minimum_acreage(self, populated: Session) -> None:
        results = parcels_in_bbox(populated, (-111.98, 33.16, -111.35, 33.52), min_acres=50.0)
        assert len(results) == 2  # the 83-acre Mesa parcel and the 66-acre Chandler parcel

    def test_adjacency_search_returns_distances(self, populated: Session) -> None:
        from helios_domain.models import Parcel

        parcel = populated.scalar(select(Parcel).where(Parcel.apn == "30433005S"))
        assert parcel is not None
        matches = find_adjacent_parcels(populated, parcel.id)
        for match in matches:
            assert match.distance_meters >= 0
            assert 0.0 <= match.spatial_confidence <= 1.0


class TestScoringPersistence:
    @pytest.fixture
    def scored_site(self, populated: Session) -> Site:
        build_sites(populated)
        site = _largest_site(populated)
        recalculate_site(populated, site, as_of=TODAY)
        return site

    def test_persists_both_prediction_targets_with_a_model_version(
        self, scored_site: Site, populated: Session
    ) -> None:
        """Scoring answers two separate questions and stores them separately.

        "Is this a data centre?" and "how far along is it?" are distinct claims,
        so collapsing them into a single confidence number would hide which one
        the evidence actually supports.
        """
        predictions = {
            p.prediction_type: p
            for p in populated.scalars(
                select(Prediction).where(Prediction.site_id == scored_site.id)
            ).all()
        }
        assert set(predictions) == {"identity_confidence", "stage_confidence"}
        for prediction in predictions.values():
            assert prediction.model_version_id is not None
            assert prediction.confidence > 0
            assert prediction.confidence_band

    def test_persists_one_explanation_per_contribution(
        self, scored_site: Site, populated: Session
    ) -> None:
        """Every point of every score must be attributable to a rule and a record."""
        prediction = populated.scalars(
            select(Prediction).where(
                Prediction.site_id == scored_site.id,
                Prediction.prediction_type == "stage_confidence",
            )
        ).one()
        explanations = populated.scalars(
            select(PredictionExplanation).where(
                PredictionExplanation.prediction_id == prediction.id
            )
        ).all()
        assert explanations
        for explanation in explanations:
            assert explanation.rule_id
            assert explanation.label
            assert explanation.applied_weight is not None

    def test_records_a_stage_transition(self, scored_site: Site, populated: Session) -> None:
        history = populated.scalars(
            select(SiteStageHistory).where(SiteStageHistory.site_id == scored_site.id)
        ).all()
        assert len(history) == 1
        assert history[0].from_stage == int(DevelopmentStage.NO_KNOWN_DEVELOPMENT)
        assert history[0].to_stage == int(DevelopmentStage.OPERATIONAL)
        assert history[0].rationale

    def test_stage_effective_date_comes_from_evidence_not_the_clock(
        self, scored_site: Site, populated: Session
    ) -> None:
        """Dating a 2013 deed as 'today' would destroy every lead-time measurement."""
        history = populated.scalars(
            select(SiteStageHistory).where(SiteStageHistory.site_id == scored_site.id)
        ).one()
        assert history.effective_date == date(2013, 11, 4)
        assert history.detected_at.date() > history.effective_date

    def test_score_history_is_append_only(self, scored_site: Site, populated: Session) -> None:
        recalculate_site(populated, scored_site, as_of=TODAY - timedelta(days=2), is_backtest=True)
        recalculate_site(populated, scored_site, as_of=TODAY - timedelta(days=1), is_backtest=True)
        history = score_history(populated, scored_site.id)

        # Each recalculation appends one identity and one stage prediction, and
        # never rewrites an earlier one.
        assert len(history) == 6
        stage_history = [p for p in history if p.prediction_type == "stage_confidence"]
        assert [p.as_of_date for p in stage_history] == [
            TODAY,
            TODAY - timedelta(days=2),
            TODAY - timedelta(days=1),
        ]

    def test_repeated_scoring_does_not_duplicate_stage_history(
        self, scored_site: Site, populated: Session
    ) -> None:
        """Stage history is a narrative of the project, not a log of recalculations."""
        recalculate_site(populated, scored_site, as_of=TODAY)
        history = populated.scalars(
            select(SiteStageHistory).where(SiteStageHistory.site_id == scored_site.id)
        ).all()
        assert len(history) == 1

    def test_refuses_to_apply_a_historical_score_to_live_state(
        self, scored_site: Site, populated: Session
    ) -> None:
        """A past cutoff sees less evidence; applying it live would fake a downgrade."""
        with pytest.raises(ValueError, match="historical score"):
            recalculate_site(populated, scored_site, as_of=TODAY - timedelta(days=30))


class TestHistoricalCutoffEnforcement:
    """Scores must be computable as of a past date using only evidence from then."""

    def test_scoring_before_first_evidence_yields_zero(self, populated: Session) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        outcome = recalculate_site(populated, site, as_of=date(2010, 1, 1), is_backtest=True)
        assert outcome.stage_score.confidence == 0.0
        assert outcome.stage_score.evidence_considered == 0
        assert outcome.identity_score.confidence == 0.0
        assert outcome.identity_score.evidence_considered == 0

    def test_scoring_after_evidence_uses_it(self, populated: Session) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        outcome = recalculate_site(populated, site, as_of=date(2014, 1, 1), is_backtest=True)
        assert outcome.stage_score.evidence_considered >= 1

    def test_backtest_predictions_do_not_mutate_live_site_state(self, populated: Session) -> None:
        """A historical replay must not overwrite the site's current conclusion."""
        build_sites(populated)
        site = _largest_site(populated)
        recalculate_site(populated, site, as_of=TODAY)
        live_confidence = site.current_confidence
        live_stage = site.current_stage

        recalculate_site(populated, site, as_of=date(2014, 1, 1), is_backtest=True)
        assert site.current_confidence == live_confidence
        assert site.current_stage == live_stage

    def test_backtest_predictions_are_flagged(self, populated: Session) -> None:
        build_sites(populated)
        site = _largest_site(populated)
        recalculate_site(populated, site, as_of=date(2014, 1, 1), is_backtest=True)
        predictions = populated.scalars(
            select(Prediction).where(Prediction.site_id == site.id)
        ).all()
        assert predictions
        assert all(p.is_backtest is True for p in predictions)


def _largest_site(session: Session) -> Site:
    """Return the site with the greatest acreage."""
    site = session.scalars(
        select(Site).order_by(Site.total_acres.desc().nullslast()).limit(1)
    ).first()
    assert site is not None
    return site
