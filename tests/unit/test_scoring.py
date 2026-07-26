"""Tests for the explainable confidence model.

Beyond arithmetic, these assert the model's *epistemic* guardrails: that a pile
of one kind of evidence cannot masquerade as corroboration, that scores decay
when a project goes quiet, and that every point of every score is attributable.
"""

from __future__ import annotations

from datetime import date

import pytest

from helios_common.vocabulary import ConfidenceBand, EvidencePolarity
from helios_domain.ontology import DevelopmentStage, StageEvidenceKind
from helios_scoring.rules import (
    DIVERSITY_CAPS,
    SCORING_RULES,
    EvidenceInput,
    infer_stage,
    model_parameters,
    model_parameters_hash,
    score_site,
)

pytestmark = pytest.mark.unit

AS_OF = date(2026, 7, 1)


def ev(
    kind: StageEvidenceKind, when: date, confidence: float = 0.9, ident: str = ""
) -> EvidenceInput:
    """Build an evidence input for testing."""
    return EvidenceInput(
        evidence_id=ident or f"{kind}-{when.isoformat()}",
        evidence_kind=str(kind),
        observed_at=when,
        confidence=confidence,
        summary=f"test evidence: {kind}",
    )


class TestEmptyAndTrivialCases:
    def test_no_evidence_yields_zero_and_stage_zero(self) -> None:
        result = score_site([], as_of=AS_OF)
        assert result.confidence == 0.0
        assert result.implied_stage is DevelopmentStage.NO_KNOWN_DEVELOPMENT
        assert result.contributions == []
        assert result.notes

    def test_future_evidence_is_excluded(self) -> None:
        """The cutoff guarantee that backtesting depends on."""
        result = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 12, 1))], as_of=AS_OF
        )
        assert result.evidence_considered == 0
        assert result.confidence == 0.0

    def test_unknown_evidence_kind_is_ignored_with_a_note(self) -> None:
        result = score_site(
            [
                EvidenceInput(
                    evidence_id="x",
                    evidence_kind="not_a_real_kind",
                    observed_at=date(2026, 1, 1),
                    confidence=1.0,
                )
            ],
            as_of=AS_OF,
        )
        assert result.confidence == 0.0
        assert any("No scoring rule" in n for n in result.notes)


class TestExplainability:
    def test_every_contribution_names_its_rule_and_evidence(self) -> None:
        """The product claim is traceability; this is the test of it."""
        result = score_site(
            [
                ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1), ident="e1"),
                ev(StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT, date(2025, 6, 1), ident="e2"),
            ],
            as_of=AS_OF,
        )
        assert len(result.contributions) == 2
        for contribution in result.contributions:
            assert contribution.rule_id
            assert contribution.evidence_id in {"e1", "e2"}
            assert contribution.label
            assert contribution.detail

    def test_contributions_sum_to_the_raw_score(self) -> None:
        result = score_site(
            [
                ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1)),
                ev(StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT, date(2025, 9, 1)),
                ev(StageEvidenceKind.PROJECT_CANCELLATION, date(2026, 2, 1)),
            ],
            as_of=AS_OF,
        )
        total = sum(c.applied_weight for c in result.contributions)
        assert total == pytest.approx(result.raw_score, abs=1e-6)

    def test_positive_and_negative_totals_are_separated(self) -> None:
        result = score_site(
            [
                ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1)),
                ev(StageEvidenceKind.PROJECT_CANCELLATION, date(2026, 2, 1)),
            ],
            as_of=AS_OF,
            target="stage",
        )
        assert result.positive_total > 0
        assert result.negative_total < 0

    def test_contributions_are_ordered_by_influence(self) -> None:
        result = score_site(
            [
                ev(StageEvidenceKind.SHELL_ENTITY_OWNERSHIP, date(2026, 1, 1)),
                ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1)),
            ],
            as_of=AS_OF,
        )
        weights = [abs(c.applied_weight) for c in result.contributions]
        assert weights == sorted(weights, reverse=True)


class TestOverconfidenceGuards:
    def test_single_evidence_kind_cannot_reach_high_confidence(self) -> None:
        """Ten permits from one office are one fact observed ten times."""
        evidence = [
            ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, i + 1), ident=f"e{i}")
            for i in range(10)
        ]
        result = score_site(evidence, as_of=AS_OF)
        assert result.distinct_kinds == 1
        assert result.confidence <= DIVERSITY_CAPS[1]

    def test_diversity_cap_engages_when_saturation_alone_is_insufficient(self) -> None:
        """With same-day evidence the occurrence cap is not enough; the ceiling binds."""
        evidence = [
            ev(StageEvidenceKind.SUBSTATION_APPLICATION, AS_OF, confidence=1.0, ident=f"e{i}")
            for i in range(5)
        ]
        result = score_site(evidence, as_of=AS_OF)
        assert result.diversity_cap_applied == DIVERSITY_CAPS[1]
        assert result.confidence == DIVERSITY_CAPS[1]
        assert any("capped" in n for n in result.notes)

    def test_diversity_raises_the_ceiling(self) -> None:
        one_kind = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1))], as_of=AS_OF
        )
        four_kinds = score_site(
            [
                ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1)),
                ev(StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT, date(2026, 1, 1)),
                ev(StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT, date(2026, 1, 1)),
                ev(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION, date(2026, 1, 1)),
            ],
            as_of=AS_OF,
        )
        assert four_kinds.confidence > one_kind.confidence
        assert four_kinds.diversity_cap_applied is None

    def test_repeat_occurrences_have_diminishing_weight(self) -> None:
        evidence = [
            ev(
                StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT,
                date(2026, 1, i + 1),
                ident=f"g{i}",
            )
            for i in range(3)
        ]
        result = score_site(evidence, as_of=AS_OF)
        weights = [c.applied_weight for c in result.contributions]
        assert weights[0] > weights[1] > weights[2]

    def test_occurrence_cap_limits_contributions(self) -> None:
        evidence = [
            ev(
                StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT,
                date(2026, 1, i + 1),
                ident=f"g{i}",
            )
            for i in range(9)
        ]
        result = score_site(evidence, as_of=AS_OF)
        rule = next(r for r in SCORING_RULES if r.rule_id == "grading-or-construction-permit")
        assert len(result.contributions) == rule.max_occurrences

    def test_score_never_exceeds_one_hundred(self) -> None:
        evidence = [
            ev(kind, date(2026, 6, 1))
            for kind in (
                StageEvidenceKind.SUBSTATION_APPLICATION,
                StageEvidenceKind.TRANSMISSION_FILING,
                StageEvidenceKind.PLANNING_APPLICATION_DATA_CENTER,
                StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT,
                StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION,
                StageEvidenceKind.WATER_OR_COOLING_PERMIT,
                StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT,
                StageEvidenceKind.DATA_CENTER_COMPATIBLE_ZONING,
            )
        ]
        result = score_site(evidence, as_of=AS_OF)
        assert 0.0 <= result.confidence <= 100.0

    def test_low_evidence_confidence_reduces_the_contribution(self) -> None:
        strong = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1), confidence=1.0)],
            as_of=AS_OF,
        )
        weak = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1), confidence=0.3)],
            as_of=AS_OF,
        )
        assert weak.confidence < strong.confidence


class TestRecencyAndStaleness:
    def test_older_evidence_contributes_less(self) -> None:
        recent = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 6, 1))], as_of=AS_OF
        )
        old = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2020, 6, 1))], as_of=AS_OF
        )
        assert old.confidence < recent.confidence

    def test_recency_multiplier_has_a_floor(self) -> None:
        """Land acquisition from a decade ago still explains why a site exists."""
        ancient = score_site(
            [ev(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION, date(2005, 1, 1))],
            as_of=AS_OF,
        )
        acquisition = next(
            c for c in ancient.contributions if c.rule_id == "large-industrial-parcel-acquisition"
        )
        assert acquisition.recency_multiplier == 0.25
        assert acquisition.applied_weight > 0

    def test_stale_site_receives_a_penalty(self) -> None:
        result = score_site(
            [ev(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION, date(2013, 11, 4))],
            as_of=AS_OF,
            target="stage",
        )
        penalties = [
            c for c in result.contributions if c.polarity is EvidencePolarity.CONTRADICTING
        ]
        assert len(penalties) == 1
        assert penalties[0].rule_id == "stale-evidence-no-progression"

    def test_active_site_receives_no_staleness_penalty(self) -> None:
        result = score_site(
            [ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 5, 1))], as_of=AS_OF
        )
        assert all(c.rule_id != "stale-evidence-no-progression" for c in result.contributions)


class TestStageInference:
    def test_takes_the_most_advanced_implied_stage(self) -> None:
        """Development is cumulative; a site under construction still has its permits."""
        result = score_site(
            [
                ev(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION, date(2024, 1, 1)),
                ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2025, 1, 1)),
                ev(StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT, date(2026, 1, 1)),
            ],
            as_of=AS_OF,
        )
        assert result.implied_stage is DevelopmentStage.CONSTRUCTION_INITIATED

    def test_land_evidence_alone_implies_speculation(self) -> None:
        result = score_site(
            [ev(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION, date(2026, 1, 1))],
            as_of=AS_OF,
        )
        assert result.implied_stage is DevelopmentStage.SITE_SPECULATION

    def test_assessor_classification_implies_operational(self) -> None:
        result = score_site(
            [ev(StageEvidenceKind.ASSESSOR_DATA_CENTER_CLASSIFICATION, date(2026, 1, 1))],
            as_of=AS_OF,
        )
        assert result.implied_stage is DevelopmentStage.OPERATIONAL

    def test_negative_contributions_do_not_advance_the_stage(self) -> None:
        result = score_site(
            [ev(StageEvidenceKind.PROJECT_CANCELLATION, date(2026, 1, 1))], as_of=AS_OF
        )
        assert result.implied_stage is DevelopmentStage.NO_KNOWN_DEVELOPMENT

    def test_infer_stage_on_empty_input(self) -> None:
        assert infer_stage([]) is DevelopmentStage.NO_KNOWN_DEVELOPMENT


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0.0, ConfidenceBand.VERY_LOW),
            (19.9, ConfidenceBand.VERY_LOW),
            (25.0, ConfidenceBand.LOW),
            (50.0, ConfidenceBand.MODERATE),
            (75.0, ConfidenceBand.HIGH),
            (95.0, ConfidenceBand.VERY_HIGH),
        ],
    )
    def test_band_boundaries(self, score: float, expected: ConfidenceBand) -> None:
        assert ConfidenceBand.from_score(score) is expected


class TestModelVersioning:
    def test_parameters_capture_every_rule(self) -> None:
        params = model_parameters()
        assert len(params["rules"]) == len(SCORING_RULES)

    def test_hash_is_stable_across_calls(self) -> None:
        assert model_parameters_hash() == model_parameters_hash()

    def test_hash_changes_when_a_weight_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Score history is only meaningful if the model identity tracks its content."""
        original = model_parameters_hash()
        monkeypatch.setattr("helios_scoring.rules.SATURATION_SCALE", 99.0)
        assert model_parameters_hash() != original


class TestDeterminism:
    def test_same_inputs_produce_the_same_score(self) -> None:
        """Reproducibility is a stated product principle, so it is tested."""
        evidence = [
            ev(StageEvidenceKind.SUBSTATION_APPLICATION, date(2026, 1, 1), ident="a"),
            ev(StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION, date(2013, 11, 4), ident="b"),
        ]
        first = score_site(evidence, as_of=AS_OF)
        second = score_site(list(reversed(evidence)), as_of=AS_OF)
        assert first.confidence == second.confidence
        assert first.raw_score == second.raw_score
