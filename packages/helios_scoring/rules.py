"""The Helios confidence model: an explainable weighted rule set.

Why rules first
---------------
There is no labelled training set yet. Fitting a model before the backtest exists
would produce numbers that look authoritative and mean nothing. A transparent
rule set can be argued with, corrected by a domain expert, and - crucially -
used as the baseline that a later statistical model must beat.

How a score is built
--------------------
Each evidence record maps to at most one rule. A rule contributes::

    applied = base_weight x confidence_multiplier x recency_multiplier

Contributions are summed and squashed into 0-100 by a saturating function, then
capped by evidence diversity. Every contribution is stored as its own
:class:`ScoreContribution`, so any point of any score can be traced to one
evidence record and one rule.

Guards against overconfidence
-----------------------------
Three mechanisms deliberately hold scores down:

* **Diversity capping.** A site supported by one kind of evidence cannot exceed
  a moderate score no matter how much of that evidence exists. Ten permits from
  one office are one fact observed ten times, not ten facts.
* **Saturation.** Contributions have diminishing returns, so a pile of weak
  signals cannot imitate a strong one.
* **Staleness.** Evidence that stops progressing decays and eventually scores
  negative, because a project that went quiet three years ago is probably dead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from helios_common.hashing import stable_json_hash
from helios_common.vocabulary import ConfidenceBand, EvidencePolarity
from helios_domain.ontology import DevelopmentStage, StageEvidenceKind

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

SCORING_MODEL_NAME = "helios-rule-based"
SCORING_MODEL_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class ScoringRule:
    """One weighted rule linking an evidence kind to a score contribution."""

    rule_id: str
    evidence_kind: StageEvidenceKind
    base_weight: float
    label: str
    rationale: str
    implies_stage: DevelopmentStage | None = None
    """The minimum stage this evidence demonstrates, when it demonstrates one."""

    max_occurrences: int = 3
    """Cap on how many matching records may contribute, limiting repetition."""

    occurrence_decay: float = 0.5
    """Multiplier applied to each additional occurrence beyond the first."""

    @property
    def polarity(self) -> EvidencePolarity:
        """Whether this rule argues for or against development."""
        return (
            EvidencePolarity.SUPPORTING if self.base_weight >= 0 else EvidencePolarity.CONTRADICTING
        )


# The weights follow the reference specification. They are starting points chosen
# by domain reasoning, not fitted values, and the methodology documentation says
# so explicitly. Calibration is deferred until a backtest exists to calibrate on.
SCORING_RULES: tuple[ScoringRule, ...] = (
    ScoringRule(
        rule_id="transmission-or-substation-filing",
        evidence_kind=StageEvidenceKind.SUBSTATION_APPLICATION,
        base_weight=25.0,
        label="Dedicated substation application",
        rationale=(
            "A utility filing for dedicated substation capacity is the most specific "
            "public signal available. It is expensive, slow, and rarely made "
            "speculatively."
        ),
        implies_stage=DevelopmentStage.REGULATORY_COMMITMENT,
    ),
    ScoringRule(
        rule_id="transmission-filing",
        evidence_kind=StageEvidenceKind.TRANSMISSION_FILING,
        base_weight=25.0,
        label="Transmission filing",
        rationale="A transmission extension filing indicates committed large-load service.",
        implies_stage=DevelopmentStage.REGULATORY_COMMITMENT,
    ),
    ScoringRule(
        rule_id="planning-application-data-center",
        evidence_kind=StageEvidenceKind.PLANNING_APPLICATION_DATA_CENTER,
        base_weight=20.0,
        label="Planning application naming data-center use",
        rationale="An applicant stating the intended use on the record is direct evidence.",
        implies_stage=DevelopmentStage.INFRASTRUCTURE_INTENT,
    ),
    ScoringRule(
        rule_id="assessor-data-center-classification",
        evidence_kind=StageEvidenceKind.ASSESSOR_DATA_CENTER_CLASSIFICATION,
        base_weight=20.0,
        label="Assessor classifies property use as data centre",
        rationale=(
            "The county assigns this class after a facility is built and assessed, so "
            "it is strong evidence of an operating facility but arrives late and cannot "
            "provide early warning."
        ),
        implies_stage=DevelopmentStage.OPERATIONAL,
    ),
    ScoringRule(
        rule_id="large-industrial-parcel-acquisition",
        evidence_kind=StageEvidenceKind.LARGE_INDUSTRIAL_PARCEL_ACQUISITION,
        base_weight=18.0,
        label="Large industrial parcel acquisition",
        rationale=(
            "Campus-scale industrial land bought by an organization is the earliest "
            "routinely observable signal, though it is also the least specific."
        ),
        implies_stage=DevelopmentStage.SITE_SPECULATION,
    ),
    ScoringRule(
        rule_id="backup-generator-air-permit",
        evidence_kind=StageEvidenceKind.BACKUP_GENERATOR_AIR_PERMIT,
        base_weight=17.0,
        label="Backup-generator air permit",
        rationale=(
            "Permits for large arrays of emergency generators are close to diagnostic: "
            "few other land uses need tens of megawatts of standby diesel."
        ),
        implies_stage=DevelopmentStage.REGULATORY_COMMITMENT,
    ),
    ScoringRule(
        rule_id="water-or-cooling-permit",
        evidence_kind=StageEvidenceKind.WATER_OR_COOLING_PERMIT,
        base_weight=14.0,
        label="Large water or cooling permit",
        rationale="Industrial cooling water demand at this scale narrows the plausible uses.",
        implies_stage=DevelopmentStage.REGULATORY_COMMITMENT,
    ),
    ScoringRule(
        rule_id="data-center-compatible-zoning",
        evidence_kind=StageEvidenceKind.DATA_CENTER_COMPATIBLE_ZONING,
        base_weight=12.0,
        label="Data-centre-compatible zoning",
        rationale="Permissive zoning is necessary but far from sufficient.",
        implies_stage=DevelopmentStage.INFRASTRUCTURE_INTENT,
    ),
    ScoringRule(
        rule_id="grading-or-construction-permit",
        evidence_kind=StageEvidenceKind.GRADING_OR_CONSTRUCTION_PERMIT,
        base_weight=10.0,
        label="Grading or construction permit",
        rationale="Ground disturbance confirms the project has moved past paperwork.",
        implies_stage=DevelopmentStage.CONSTRUCTION_INITIATED,
    ),
    ScoringRule(
        rule_id="dust-control-registration",
        evidence_kind=StageEvidenceKind.DUST_CONTROL_REGISTRATION,
        base_weight=10.0,
        label="Dust-control registration",
        rationale="Required before earth-moving in Maricopa County; a construction proxy.",
        implies_stage=DevelopmentStage.CONSTRUCTION_INITIATED,
    ),
    ScoringRule(
        rule_id="satellite-construction-change",
        evidence_kind=StageEvidenceKind.SATELLITE_CONSTRUCTION_CHANGE,
        base_weight=8.0,
        label="Satellite-observed construction change",
        rationale=(
            "Imagery corroborates activity but cannot identify its purpose, so it "
            "supports a stage rather than establishing one."
        ),
        implies_stage=DevelopmentStage.CONSTRUCTION_INITIATED,
    ),
    ScoringRule(
        rule_id="dedicated-substation-proximity",
        evidence_kind=StageEvidenceKind.DEDICATED_SUBSTATION_PROXIMITY,
        base_weight=8.0,
        label="High-voltage substation in close proximity",
        rationale=(
            "Nearby transmission-class capacity makes a site viable. This is a "
            "locational precondition, not an indication that anything is happening."
        ),
    ),
    ScoringRule(
        rule_id="known-developer-relationship",
        evidence_kind=StageEvidenceKind.KNOWN_DEVELOPER_RELATIONSHIP,
        base_weight=7.0,
        label="Relationship to a known data-centre developer",
        rationale="Prior developments by the same party raise the prior, weakly.",
    ),
    ScoringRule(
        rule_id="shell-entity-ownership",
        evidence_kind=StageEvidenceKind.SHELL_ENTITY_OWNERSHIP,
        base_weight=6.0,
        label="Single-purpose entity holds title",
        rationale=(
            "Project-specific LLCs are routine in large development and also routine "
            "in ordinary commercial real estate. Weighted low on purpose: this must "
            "never approach being an attribution."
        ),
        implies_stage=DevelopmentStage.SITE_SPECULATION,
    ),
    ScoringRule(
        rule_id="hiring-or-procurement-signal",
        evidence_kind=StageEvidenceKind.HIRING_OR_PROCUREMENT_SIGNAL,
        base_weight=5.0,
        label="Hiring or procurement activity",
        rationale="Staffing activity suggests an approach to operation.",
        implies_stage=DevelopmentStage.OPERATIONAL,
    ),
    ScoringRule(
        rule_id="conflicting-facility-classification",
        evidence_kind=StageEvidenceKind.CONFLICTING_FACILITY_CLASSIFICATION,
        base_weight=-10.0,
        label="Conflicting facility classification",
        rationale="A source describing a different land use undercuts the hypothesis.",
    ),
    ScoringRule(
        rule_id="project-cancellation",
        evidence_kind=StageEvidenceKind.PROJECT_CANCELLATION,
        base_weight=-15.0,
        label="Project cancellation or withdrawal",
        rationale="A withdrawn application is direct negative evidence.",
    ),
    ScoringRule(
        rule_id="stale-evidence-no-progression",
        evidence_kind=StageEvidenceKind.STALE_EVIDENCE_NO_PROGRESSION,
        base_weight=-20.0,
        label="Stale evidence with no progression",
        rationale=(
            "Applied automatically when the newest evidence is older than the "
            "staleness threshold. Projects that stop generating records have usually "
            "stalled, and a score that never decays would overstate the pipeline."
        ),
    ),
)

RULES_BY_KIND: dict[str, ScoringRule] = {str(r.evidence_kind): r for r in SCORING_RULES}

STALENESS_THRESHOLD_DAYS = 900
"""Roughly 2.5 years. Long enough to span normal permitting gaps in Arizona,
short enough that abandoned projects eventually fall out of the pipeline."""

RECENCY_HALF_LIFE_DAYS = 730
"""Evidence retains half its weight after two years. Land records stay relevant
far longer than news, so the decay is deliberately gentle."""

DIVERSITY_CAPS: dict[int, float] = {
    1: 45.0,
    2: 70.0,
    3: 88.0,
}
"""Maximum confidence permitted given the number of distinct evidence kinds.

A single kind of evidence, however abundant, cannot produce high confidence.
Four or more distinct kinds are uncapped."""

SATURATION_SCALE = 60.0
"""Controls how quickly summed weight approaches 100. At this many points the
score reaches roughly 63."""


STANDING_CONDITION_KINDS: frozenset[str] = frozenset(
    {
        str(StageEvidenceKind.ASSESSOR_DATA_CENTER_CLASSIFICATION),
        str(StageEvidenceKind.DATA_CENTER_COMPATIBLE_ZONING),
        str(StageEvidenceKind.DEDICATED_SUBSTATION_PROXIMITY),
        str(StageEvidenceKind.HIGH_VOLTAGE_TRANSMISSION_PROXIMITY),
    }
)
"""Evidence describing a current state rather than a past event.

Standing conditions are exempt from recency decay: the county's classification of
a parcel is re-asserted every assessment cycle, so it does not become less true
with age the way a two-year-old rezoning application becomes less indicative."""


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    """Minimal view of an evidence record needed for scoring.

    Deliberately decoupled from the ORM so scoring can be unit-tested with no
    database and replayed against historical snapshots.
    """

    evidence_id: str
    evidence_kind: str
    observed_at: date
    confidence: float
    summary: str = ""
    polarity: str = str(EvidencePolarity.SUPPORTING)

    @property
    def is_standing_condition(self) -> bool:
        """Whether this evidence describes a current state rather than an event."""
        return self.evidence_kind in STANDING_CONDITION_KINDS


@dataclass(frozen=True, slots=True)
class ScoreContribution:
    """One rule firing against one evidence record."""

    rule_id: str
    evidence_id: str | None
    evidence_kind: str
    label: str
    detail: str
    base_weight: float
    applied_weight: float
    confidence_multiplier: float
    recency_multiplier: float
    polarity: EvidencePolarity


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """A complete, explained confidence score."""

    raw_score: float
    confidence: float
    band: ConfidenceBand
    contributions: list[ScoreContribution]
    positive_total: float
    negative_total: float
    evidence_considered: int
    distinct_kinds: int
    implied_stage: DevelopmentStage
    diversity_cap_applied: float | None
    as_of: date
    model_name: str = SCORING_MODEL_NAME
    model_version: str = SCORING_MODEL_VERSION
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """One-line explanation suitable for an API response."""
        return (
            f"{self.confidence:.0f}% confidence from {self.evidence_considered} evidence "
            f"records across {self.distinct_kinds} distinct kinds; stage "
            f"{self.implied_stage.value} ({self.implied_stage.label})."
        )


def _recency_multiplier(observed: date, as_of: date) -> float:
    """Exponential decay by age, floored so old evidence never becomes worthless.

    Land acquisition from 2013 still matters in 2026 - it is why the parcel is
    where it is - so the floor is comparatively high at 0.25.
    """
    age_days = max(0, (as_of - observed).days)
    decay = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
    return round(max(0.25, decay), 4)


def _saturate(total: float) -> float:
    """Map an unbounded positive weight sum onto 0-100 with diminishing returns.

    Uses ``100 * (1 - exp(-x / scale))``, which is monotonic, smooth, and cannot
    exceed 100 no matter how much evidence accumulates.
    """
    import math

    if total <= 0:
        return 0.0
    return 100.0 * (1.0 - math.exp(-total / SATURATION_SCALE))


def score_site(
    evidence: Sequence[EvidenceInput],
    *,
    as_of: date,
    staleness_threshold_days: int = STALENESS_THRESHOLD_DAYS,
) -> ScoreResult:
    """Compute an explained confidence score for a site.

    Args:
        evidence: Evidence records to consider. The caller is responsible for
            having already filtered by any backtest cutoff.
        as_of: The date the score is computed as of; drives recency and staleness.
        staleness_threshold_days: Age beyond which a lack of progression penalises.

    Returns:
        The score with a full contribution breakdown.
    """
    usable = [e for e in evidence if e.observed_at <= as_of]
    contributions: list[ScoreContribution] = []
    notes: list[str] = []

    if not usable:
        return ScoreResult(
            raw_score=0.0,
            confidence=0.0,
            band=ConfidenceBand.VERY_LOW,
            contributions=[],
            positive_total=0.0,
            negative_total=0.0,
            evidence_considered=0,
            distinct_kinds=0,
            implied_stage=DevelopmentStage.NO_KNOWN_DEVELOPMENT,
            diversity_cap_applied=None,
            as_of=as_of,
            notes=["No evidence available on or before the scoring date."],
        )

    # Newest first, so that when a rule's occurrence cap bites it keeps the most
    # recent instances rather than an arbitrary subset.
    ordered = sorted(usable, key=lambda e: e.observed_at, reverse=True)
    occurrences: dict[str, int] = {}

    for record in ordered:
        rule = RULES_BY_KIND.get(record.evidence_kind)
        if rule is None:
            notes.append(f"No scoring rule for evidence kind {record.evidence_kind!r}; ignored.")
            continue

        seen = occurrences.get(rule.rule_id, 0)
        if seen >= rule.max_occurrences:
            continue
        occurrences[rule.rule_id] = seen + 1

        occurrence_multiplier = rule.occurrence_decay**seen
        confidence_multiplier = round(max(0.0, min(1.0, record.confidence)), 4)
        recency_multiplier = (
            1.0 if record.is_standing_condition else _recency_multiplier(record.observed_at, as_of)
        )
        applied = (
            rule.base_weight * confidence_multiplier * recency_multiplier * occurrence_multiplier
        )

        detail = record.summary or rule.rationale
        if seen:
            detail = f"{detail} (occurrence {seen + 1}, weight reduced)"

        contributions.append(
            ScoreContribution(
                rule_id=rule.rule_id,
                evidence_id=record.evidence_id,
                evidence_kind=record.evidence_kind,
                label=rule.label,
                detail=detail,
                base_weight=rule.base_weight,
                applied_weight=round(applied, 4),
                confidence_multiplier=confidence_multiplier,
                recency_multiplier=recency_multiplier,
                polarity=rule.polarity,
            )
        )

    staleness = _staleness_contribution(ordered, as_of, staleness_threshold_days)
    if staleness is not None:
        contributions.append(staleness)
        notes.append(
            f"Newest evidence is older than {staleness_threshold_days} days; "
            "a staleness penalty was applied."
        )

    positive_total = sum(c.applied_weight for c in contributions if c.applied_weight > 0)
    negative_total = sum(c.applied_weight for c in contributions if c.applied_weight < 0)

    raw_score = positive_total + negative_total
    confidence = _saturate(raw_score)

    distinct_kinds = len({c.evidence_kind for c in contributions if c.applied_weight > 0})
    cap = DIVERSITY_CAPS.get(distinct_kinds)
    cap_applied: float | None = None
    if cap is not None and confidence > cap:
        cap_applied = cap
        confidence = cap
        notes.append(
            f"Confidence capped at {cap:.0f} because only {distinct_kinds} distinct "
            "evidence kind(s) support this site. Repetition of one kind of record is "
            "not corroboration."
        )

    confidence = round(max(0.0, min(100.0, confidence)), 2)

    return ScoreResult(
        raw_score=round(raw_score, 4),
        confidence=confidence,
        band=ConfidenceBand.from_score(confidence),
        contributions=sorted(contributions, key=lambda c: abs(c.applied_weight), reverse=True),
        positive_total=round(positive_total, 4),
        negative_total=round(negative_total, 4),
        evidence_considered=len(usable),
        distinct_kinds=distinct_kinds,
        implied_stage=infer_stage(contributions),
        diversity_cap_applied=cap_applied,
        as_of=as_of,
        notes=notes,
    )


def _staleness_contribution(
    ordered_evidence: Sequence[EvidenceInput], as_of: date, threshold_days: int
) -> ScoreContribution | None:
    """Build the staleness penalty when a site has stopped producing records.

    The penalty models an abandoned *project*, so it is measured against event
    evidence only. A standing condition - the county still classifying a parcel
    as a data centre - means the facility exists now, and an existing facility
    does not become less likely to exist as its purchase deed ages.
    """
    events = [e for e in ordered_evidence if not e.is_standing_condition]
    if not events or any(e.is_standing_condition for e in ordered_evidence):
        return None

    newest = events[0].observed_at
    age_days = (as_of - newest).days
    if age_days <= threshold_days:
        return None

    rule = RULES_BY_KIND[str(StageEvidenceKind.STALE_EVIDENCE_NO_PROGRESSION)]
    return ScoreContribution(
        rule_id=rule.rule_id,
        evidence_id=None,
        evidence_kind=str(StageEvidenceKind.STALE_EVIDENCE_NO_PROGRESSION),
        label=rule.label,
        detail=(
            f"Most recent evidence is {age_days} days old "
            f"({newest.isoformat()}), beyond the {threshold_days}-day staleness threshold."
        ),
        base_weight=rule.base_weight,
        applied_weight=rule.base_weight,
        confidence_multiplier=1.0,
        recency_multiplier=1.0,
        polarity=EvidencePolarity.CONTRADICTING,
    )


def infer_stage(contributions: Iterable[ScoreContribution]) -> DevelopmentStage:
    """Derive the development stage implied by the contributing evidence.

    The stage is the **highest** stage any positively-contributing rule implies.
    Development is cumulative - a site under construction still has its permits -
    so taking the maximum reflects how far the project has demonstrably got,
    rather than averaging away the most advanced evidence.

    Args:
        contributions: Score contributions from :func:`score_site`.

    Returns:
        The implied stage.
    """
    stage = DevelopmentStage.NO_KNOWN_DEVELOPMENT
    for contribution in contributions:
        if contribution.applied_weight <= 0:
            continue
        rule = next((r for r in SCORING_RULES if r.rule_id == contribution.rule_id), None)
        if rule and rule.implies_stage and rule.implies_stage > stage:
            stage = rule.implies_stage
    return stage


def model_parameters() -> dict[str, object]:
    """Serialise the model configuration for storage on ``model_versions``.

    Persisting the full parameter set means a historical score can be understood
    even after the rules change, which is what makes score history meaningful.
    """
    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "evidence_kind": str(r.evidence_kind),
                "base_weight": r.base_weight,
                "implies_stage": r.implies_stage.value if r.implies_stage else None,
                "max_occurrences": r.max_occurrences,
                "occurrence_decay": r.occurrence_decay,
            }
            for r in SCORING_RULES
        ],
        "staleness_threshold_days": STALENESS_THRESHOLD_DAYS,
        "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
        "diversity_caps": DIVERSITY_CAPS,
        "saturation_scale": SATURATION_SCALE,
    }


def model_parameters_hash() -> str:
    """Content hash of the model configuration, used as its identity."""
    return stable_json_hash(model_parameters())


__all__ = [
    "DIVERSITY_CAPS",
    "RECENCY_HALF_LIFE_DAYS",
    "RULES_BY_KIND",
    "SCORING_MODEL_NAME",
    "SCORING_MODEL_VERSION",
    "SCORING_RULES",
    "STALENESS_THRESHOLD_DAYS",
    "EvidenceInput",
    "ScoreContribution",
    "ScoreResult",
    "ScoringRule",
    "infer_stage",
    "model_parameters",
    "model_parameters_hash",
    "score_site",
]
