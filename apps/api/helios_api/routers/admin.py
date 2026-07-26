"""Administrative operations: connector runs, review actions, recalculation.

Every route here mutates state and is guarded by the admin bearer token, which
is refused outright when unconfigured. Review actions write a
:class:`HumanReview` audit row, because a human overriding a machine conclusion
is itself a fact the system must be able to explain later.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from helios_api.deps import AdminPrincipal, AppSettings, DbSession
from helios_api.schemas import PredictionResponse
from helios_api.serializers import serialize_prediction
from helios_common.evidence_store import build_evidence_store
from helios_common.time import utcnow
from helios_common.vocabulary import ConnectorStatus, HumanReviewStatus
from helios_connectors.pipeline import IngestionPipeline
from helios_connectors.registry import get_entry
from helios_connectors.sync import sync_registry
from helios_domain.models import EvidenceRecord, HumanReview, Site, SourceConnector

router = APIRouter(prefix="/admin", tags=["admin"])


class ReviewRequest(BaseModel):
    """A human review decision."""

    decision: str = Field(description="confirmed | rejected | needs_more_evidence")
    rationale: str | None = None
    reviewer: str = "admin"


class ConnectorRunRequest(BaseModel):
    """Parameters for a manual connector run."""

    where: str | None = Field(
        default=None, description="Attribute filter passed to the connector, if supported."
    )
    bbox: list[float] | None = Field(
        default=None, description="[min_lon, min_lat, max_lon, max_lat]"
    )


_CONNECTOR_CLASSES: dict[str, str] = {
    "maricopa-assessor-parcels": "helios_connectors.maricopa_assessor:MaricopaAssessorConnector",
    "osm-power-infrastructure": "helios_connectors.osm_power:OsmPowerConnector",
    "epa-echo-air-facilities": "helios_connectors.epa_echo:EpaEchoAirConnector",
    "azcc-edocket": "helios_connectors.azcc_edocket:AzccEdocketConnector",
}


def _load_connector_class(entry_point: str) -> Any:
    """Import a connector class from its dotted entry point."""
    import importlib

    module_name, class_name = entry_point.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


@router.post(
    "/registry/sync", summary="Synchronise the declarative source registry into the database"
)
def sync_source_registry(session: DbSession, _principal: AdminPrincipal) -> dict[str, int]:
    """Project the version-controlled source registry into the database."""
    result = sync_registry(session)
    session.commit()
    return result


@router.post("/connectors/{connector_slug}/run", summary="Run a connector")
def run_connector(
    session: DbSession,
    settings: AppSettings,
    _principal: AdminPrincipal,
    connector_slug: str,
    request: Annotated[ConnectorRunRequest, Body()] = ConnectorRunRequest(),
) -> dict[str, Any]:
    """Execute a connector synchronously and return its run summary.

    Runs are synchronous because the MVP's measured ingestion volume does not
    justify a task queue. A connector taking minutes is acceptable for an
    operator-triggered action; when scheduled ingestion needs to outlive an HTTP
    request, a queue becomes justified.
    """
    if connector_slug not in _CONNECTOR_CLASSES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No runnable connector {connector_slug!r}. Available: "
                f"{sorted(_CONNECTOR_CLASSES)}"
            ),
        )

    connector_row = session.scalar(
        select(SourceConnector).where(SourceConnector.slug == connector_slug)
    )
    if connector_row is not None and not connector_row.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Connector {connector_slug!r} is disabled.",
        )

    entry = get_entry(connector_slug)
    connector_class = _load_connector_class(_CONNECTOR_CLASSES[connector_slug])

    kwargs: dict[str, Any] = {}
    if connector_slug != "azcc-edocket":
        if request.where is not None:
            kwargs["where"] = request.where
        if request.bbox is not None:
            if len(request.bbox) != 4:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="bbox must contain exactly four values",
                )
            kwargs["bbox"] = tuple(request.bbox)

    connector = connector_class(settings=settings, **kwargs)
    mode = "fixture" if connector.get_metadata().status == ConnectorStatus.FIXTURE_ONLY else "live"
    try:
        summary = IngestionPipeline(
            session,
            connector,
            build_evidence_store(settings),
            mode=mode,
            trigger="api",
        ).run()
        session.commit()
    finally:
        connector.close()

    return {"connector": entry.slug, **summary.as_dict()}


@router.post("/evidence/{evidence_id}/review", summary="Record a human review of evidence")
def review_evidence(
    session: DbSession,
    _principal: AdminPrincipal,
    evidence_id: UUID,
    request: Annotated[ReviewRequest, Body()],
) -> dict[str, Any]:
    """Set an evidence record's review status and write an audit row."""
    valid = {
        str(HumanReviewStatus.CONFIRMED),
        str(HumanReviewStatus.REJECTED),
        str(HumanReviewStatus.NEEDS_MORE_EVIDENCE),
    }
    if request.decision not in valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"decision must be one of {sorted(valid)}",
        )

    record = session.get(EvidenceRecord, evidence_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No evidence with id {evidence_id}"
        )

    previous = record.human_review_status
    record.human_review_status = request.decision
    session.add(
        HumanReview(
            target_table="evidence_records",
            target_id=record.id,
            reviewer=request.reviewer,
            decision=request.decision,
            previous_status=previous,
            rationale=request.rationale,
            reviewed_at=utcnow(),
        )
    )
    session.commit()

    return {
        "evidence_id": str(record.id),
        "previous_status": previous,
        "current_status": record.human_review_status,
    }


@router.post(
    "/sites/{site_id}/recalculate",
    response_model=PredictionResponse,
    summary="Recalculate a site's confidence score",
)
def recalculate(
    session: DbSession, _principal: AdminPrincipal, site_id: UUID
) -> PredictionResponse:
    """Rescore a site against current evidence and return the new prediction."""
    from helios_domain.models import Prediction
    from helios_scoring.service import recalculate_site

    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No site with id {site_id}"
        )

    outcome = recalculate_site(session, site)
    session.commit()

    prediction = session.get(Prediction, outcome.prediction_id)
    if prediction is None:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction was not persisted",
        )
    return serialize_prediction(session, prediction)


@router.post("/sites/rebuild", summary="Rebuild sites from the current parcel population")
def rebuild_sites(session: DbSession, _principal: AdminPrincipal) -> dict[str, Any]:
    """Re-run site clustering and infrastructure linking."""
    from helios_geospatial.site_builder import build_sites

    result = build_sites(session)
    session.commit()
    return {
        "sites_created": result.sites_created,
        "sites_updated": result.sites_updated,
        "parcels_linked": result.parcels_linked,
        "evidence_attached": result.evidence_attached,
        "dependencies_created": result.dependencies_created,
    }


__all__ = ["router"]
