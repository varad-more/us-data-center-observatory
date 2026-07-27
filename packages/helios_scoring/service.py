"""Persistence of scores, explanations, and stage transitions.

Scoring is append-only. Recalculating a site writes a new :class:`Prediction`
with its own explanation rows rather than mutating the previous one, which is
what makes "how did this score change, and why?" answerable after the fact.

Stage transitions are recorded only when the stage actually moves, so
``site_stage_history`` stays a narrative of the project rather than a log of
every recalculation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import select

from helios_common.logging import get_logger
from helios_common.time import utcnow
from helios_domain.models import (
    EvidenceRecord,
    ModelVersion,
    Prediction,
    PredictionExplanation,
    Site,
    SiteEstimate,
    SiteStageHistory,
)
from helios_domain.ontology import DevelopmentStage
from helios_scoring.impact import ImpactEstimate, estimate_power_mw, estimate_water_gpd
from helios_scoring.rules import (
    SCORING_MODEL_NAME,
    SCORING_MODEL_VERSION,
    EvidenceInput,
    ScoreResult,
    model_parameters,
    model_parameters_hash,
    score_site,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RecalculationOutcome:
    """What a recalculation produced."""

    identity_prediction_id: uuid.UUID
    stage_prediction_id: uuid.UUID
    identity_score: ScoreResult
    stage_score: ScoreResult
    stage_changed: bool
    previous_stage: DevelopmentStage | None
    new_stage: DevelopmentStage
    is_downgrade: bool


def get_or_create_model_version(session: Session) -> ModelVersion:
    """Fetch the active scoring-model row, creating it if the rules are new.

    The row is keyed on name and version, and carries a hash of the full
    parameter set. If the rules change without a version bump, the hash mismatch
    is recorded in the calibration notes rather than silently overwriting - a
    stored score must always be interpretable against the rules that produced it.

    Args:
        session: Open database session.

    Returns:
        The model-version row.
    """
    parameters = model_parameters()
    parameters_hash = model_parameters_hash()

    model = session.scalar(
        select(ModelVersion).where(
            ModelVersion.name == SCORING_MODEL_NAME,
            ModelVersion.version == SCORING_MODEL_VERSION,
        )
    )
    if model is None:
        model = ModelVersion(
            name=SCORING_MODEL_NAME,
            version=SCORING_MODEL_VERSION,
            model_kind="rule_based",
            description=(
                "Weighted, explainable rule set over evidence kinds. Weights are "
                "domain-reasoned starting points, not fitted values; calibration is "
                "deferred until a historical backtest exists."
            ),
            parameters=parameters,
            parameters_hash=parameters_hash,
            is_active=True,
        )
        session.add(model)
        session.flush()
    elif model.parameters_hash != parameters_hash:
        logger.warning(
            "scoring.model_parameters_changed_without_version_bump",
            model=SCORING_MODEL_NAME,
            version=SCORING_MODEL_VERSION,
        )
        model.calibration_notes = (
            f"Parameter hash changed from {model.parameters_hash[:12]} to "
            f"{parameters_hash[:12]} without a version bump; historical scores under "
            "this version may not be reproducible."
        )
    return model


def load_evidence_inputs(
    session: Session, site_id: uuid.UUID, *, as_of: date | None = None
) -> list[EvidenceInput]:
    """Load a site's evidence, optionally restricted to a historical cutoff.

    The ``as_of`` filter applies to ``observed_at``, the date the evidence
    pertains to, and not to ``created_at``, the date Helios ingested it. Using
    the ingestion date would leak the present into a historical replay.

    Args:
        session: Open database session.
        site_id: Site whose evidence to load.
        as_of: Exclude evidence observed after this date.

    Returns:
        Scoring inputs ordered oldest first.
    """
    statement = select(EvidenceRecord).where(EvidenceRecord.site_id == site_id)
    if as_of is not None:
        statement = statement.where(EvidenceRecord.observed_at <= as_of)

    return [
        EvidenceInput(
            evidence_id=str(record.id),
            evidence_kind=record.evidence_kind,
            observed_at=record.observed_at,
            confidence=record.confidence,
            summary=record.summary,
            polarity=record.polarity,
        )
        for record in session.scalars(statement.order_by(EvidenceRecord.observed_at)).all()
    ]


def recalculate_site(
    session: Session,
    site: Site,
    *,
    as_of: date | None = None,
    is_backtest: bool = False,
) -> RecalculationOutcome:
    """Score a site, persist the explained prediction, and record any stage change.

    Args:
        session: Open database session.
        site: The site to score.
        as_of: Evidence cutoff; defaults to today.
        is_backtest: Marks the prediction as a historical replay so it can be
            excluded from live views.

    Returns:
        The outcome, including whether the stage moved.

    Raises:
        ValueError: If a historical cutoff is requested without ``is_backtest``.
            Scoring a past date necessarily sees less evidence, so applying the
            result to live site state would record a spurious downgrade and
            corrupt the stage history.
    """
    today = utcnow().date()
    cutoff = as_of or today
    if cutoff < today and not is_backtest:
        raise ValueError(
            f"Refusing to apply a historical score (as_of={cutoff.isoformat()}) to live "
            "site state. Pass is_backtest=True for historical replays."
        )

    model = get_or_create_model_version(session)
    evidence = load_evidence_inputs(session, site.id, as_of=cutoff)
    identity_result = score_site(evidence, as_of=cutoff, target="identity")
    stage_result = score_site(evidence, as_of=cutoff, target="stage")

    identity_prediction = Prediction(
        site_id=site.id,
        model_version_id=model.id,
        prediction_type="identity_confidence",
        calculated_at=utcnow(),
        as_of_date=cutoff,
        predicted_stage=int(identity_result.implied_stage),
        raw_score=identity_result.raw_score,
        confidence=identity_result.confidence,
        confidence_band=str(identity_result.band),
        positive_contribution=identity_result.positive_total,
        negative_contribution=identity_result.negative_total,
        evidence_considered=identity_result.evidence_considered,
        distinct_evidence_kinds=identity_result.distinct_kinds,
        is_backtest=is_backtest,
        summary=identity_result.summary,
    )

    stage_prediction = Prediction(
        site_id=site.id,
        model_version_id=model.id,
        prediction_type="stage_confidence",
        calculated_at=utcnow(),
        as_of_date=cutoff,
        predicted_stage=int(stage_result.implied_stage),
        raw_score=stage_result.raw_score,
        confidence=stage_result.confidence,
        confidence_band=str(stage_result.band),
        positive_contribution=stage_result.positive_total,
        negative_contribution=stage_result.negative_total,
        evidence_considered=stage_result.evidence_considered,
        distinct_evidence_kinds=stage_result.distinct_kinds,
        is_backtest=is_backtest,
        summary=stage_result.summary,
    )

    session.add_all([identity_prediction, stage_prediction])
    session.flush()

    for order, contribution in enumerate(identity_result.contributions):
        session.add(
            PredictionExplanation(
                prediction_id=identity_prediction.id,
                evidence_record_id=(
                    uuid.UUID(contribution.evidence_id) if contribution.evidence_id else None
                ),
                rule_id=contribution.rule_id,
                evidence_kind=contribution.evidence_kind,
                label=contribution.label,
                detail=contribution.detail,
                base_weight=contribution.base_weight,
                applied_weight=contribution.applied_weight,
                confidence_multiplier=contribution.confidence_multiplier,
                recency_multiplier=contribution.recency_multiplier,
                polarity=str(contribution.polarity),
                display_order=order,
            )
        )

    for order, contribution in enumerate(stage_result.contributions):
        session.add(
            PredictionExplanation(
                prediction_id=stage_prediction.id,
                evidence_record_id=(
                    uuid.UUID(contribution.evidence_id) if contribution.evidence_id else None
                ),
                rule_id=contribution.rule_id,
                evidence_kind=contribution.evidence_kind,
                label=contribution.label,
                detail=contribution.detail,
                base_weight=contribution.base_weight,
                applied_weight=contribution.applied_weight,
                confidence_multiplier=contribution.confidence_multiplier,
                recency_multiplier=contribution.recency_multiplier,
                polarity=str(contribution.polarity),
                display_order=order,
            )
        )

    previous_stage = DevelopmentStage(site.current_stage)
    new_stage = stage_result.implied_stage
    stage_changed = new_stage != previous_stage

    if not is_backtest:
        site.current_confidence = identity_result.confidence
        site.stage_confidence = stage_result.confidence
        site.score_last_calculated_at = identity_prediction.calculated_at
        if stage_changed:
            _record_stage_transition(
                session,
                site=site,
                previous=previous_stage,
                new=new_stage,
                result=stage_result,
                model=model,
            )

        # Update estimates
        session.query(SiteEstimate).filter(SiteEstimate.site_id == site.id).delete()

        # total_acres is a Decimal column; the estimator works in float.
        acres = float(site.total_acres) if site.total_acres is not None else None
        power = estimate_power_mw(acres, int(new_stage))
        if power is not None:
            session.add(_estimate_row(site.id, "power_capacity", power))
            water = estimate_water_gpd(power)
            if water is not None:
                session.add(_estimate_row(site.id, "water_usage", water))

    session.flush()
    logger.info(
        "scoring.recalculated",
        site=site.project_code,
        identity_confidence=identity_result.confidence,
        stage_confidence=stage_result.confidence,
        stage=int(new_stage),
        stage_changed=stage_changed,
        as_of=cutoff.isoformat(),
    )

    return RecalculationOutcome(
        identity_prediction_id=identity_prediction.id,
        stage_prediction_id=stage_prediction.id,
        identity_score=identity_result,
        stage_score=stage_result,
        stage_changed=stage_changed,
        previous_stage=previous_stage,
        new_stage=new_stage,
        is_downgrade=new_stage < previous_stage,
    )


def _estimate_row(site_id: uuid.UUID, estimate_type: str, estimate: ImpactEstimate) -> SiteEstimate:
    """Persist a ranged estimate with the assumptions that produced it.

    `SiteEstimate` was built to carry a range, a method and its assumptions. It
    had been receiving a bare `likely_value`, which rendered a heuristic as
    though it were a measurement.

    The class is `inferred` rather than `calculated` for the reason recorded in
    tasks/lessons.md: the arithmetic is exact but the coefficients are industry
    assumptions, and a value is only as strong as its weakest input.
    """
    return SiteEstimate(
        site_id=site_id,
        estimate_type=estimate_type,
        unit=estimate.unit,
        lower_value=estimate.lower,
        likely_value=estimate.likely,
        upper_value=estimate.upper,
        method=estimate.method,
        assumptions=estimate.assumptions,
        assertion_class="inferred",
        calculated_at=utcnow(),
    )


def _record_stage_transition(
    session: Session,
    *,
    site: Site,
    previous: DevelopmentStage,
    new: DevelopmentStage,
    result: ScoreResult,
    model: ModelVersion,
) -> SiteStageHistory:
    """Append a stage transition to the site's history.

    The effective date is taken from the evidence that justifies the new stage,
    not from the clock. A permit issued in 2019 that Helios only ingests today
    means the site *reached* that stage in 2019; recording it as today would
    destroy the lead-time measurements the project exists to produce.
    """
    triggering = [
        c for c in result.contributions if c.applied_weight > 0 and c.evidence_id is not None
    ]
    effective = _effective_date_for_stage(session, triggering) or result.as_of

    history = SiteStageHistory(
        site_id=site.id,
        from_stage=int(previous),
        to_stage=int(new),
        effective_date=effective,
        detected_at=utcnow(),
        is_downgrade=new < previous,
        confidence=result.confidence,
        rationale=_transition_rationale(previous, new, result),
        triggering_evidence_ids=[c.evidence_id for c in triggering if c.evidence_id],
        model_version_id=model.id,
    )
    session.add(history)

    site.current_stage = int(new)
    site.stage_last_changed_at = history.detected_at
    return history


def _effective_date_for_stage(session: Session, contributions: list) -> date | None:
    """Find the earliest observation date among the evidence driving a transition."""
    ids = [uuid.UUID(c.evidence_id) for c in contributions if c.evidence_id]
    if not ids:
        return None
    dates = session.scalars(
        select(EvidenceRecord.observed_at).where(EvidenceRecord.id.in_(ids))
    ).all()
    return min(dates) if dates else None


def _transition_rationale(
    previous: DevelopmentStage, new: DevelopmentStage, result: ScoreResult
) -> str:
    """Compose a human-readable explanation of why the stage moved."""
    direction = "downgraded" if new < previous else "advanced"
    drivers = [c.label for c in result.contributions if c.applied_weight > 0][:3]
    driver_text = "; ".join(drivers) if drivers else "no positive evidence"
    return (
        f"Stage {direction} from {previous.value} ({previous.label}) to "
        f"{new.value} ({new.label}) at {result.confidence:.0f}% confidence. "
        f"Principal evidence: {driver_text}."
    )


def score_history(session: Session, site_id: uuid.UUID) -> list[Prediction]:
    """Return every prediction for a site, oldest first.

    Args:
        session: Open database session.
        site_id: The site.

    Returns:
        Predictions in chronological order.
    """
    return list(
        session.scalars(
            select(Prediction)
            .where(Prediction.site_id == site_id)
            .order_by(Prediction.calculated_at)
        ).all()
    )


__all__ = [
    "RecalculationOutcome",
    "get_or_create_model_version",
    "load_evidence_inputs",
    "recalculate_site",
    "score_history",
]
