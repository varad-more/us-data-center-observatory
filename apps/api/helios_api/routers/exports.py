"""Data exports, including the downloadable evidence bundle.

The evidence bundle is the reproducibility deliverable. It contains everything a
third party needs to check a Helios conclusion without trusting Helios: the site
profile, every evidence record with its provenance, the scoring model parameters
that produced the confidence figure, and the SHA-256 of each source document so
the original bytes can be verified independently.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from helios_api.deps import DbSession
from helios_api.serializers import (
    collect_attributions,
    geometry_to_geojson,
    serialize_evidence,
    serialize_prediction,
    serialize_stage_transition,
)
from helios_common.time import utcnow
from helios_domain.models import (
    DocumentVersion,
    EvidenceRecord,
    Parcel,
    Prediction,
    Site,
    SiteParcelLink,
    SiteStageHistory,
    Source,
    SourceDocument,
)
from helios_domain.ontology import DevelopmentStage
from helios_scoring.rules import (
    SCORING_MODEL_NAME,
    SCORING_MODEL_VERSION,
    model_parameters,
    model_parameters_hash,
)

router = APIRouter(prefix="/exports", tags=["exports"])

DISCLAIMER = (
    "Helios infers development activity from public records. Confidence scores are "
    "model output, not fact. Helios does not assert the identity of any facility "
    "operator unless a direct filing establishes it. Estimates are labelled as such "
    "and must not be cited as measurements."
)


def _get_site_or_404(session: DbSession, site_id: UUID) -> Site:
    site = session.get(Site, site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No site with id {site_id}"
        )
    return site


@router.get("/sites.csv", summary="Export sites as CSV")
def export_sites_csv(
    session: DbSession,
    region: Annotated[str | None, Query()] = None,
) -> Response:
    """Export the site register as CSV."""
    statement = select(Site).order_by(Site.current_confidence.desc().nullslast())
    if region:
        statement = statement.where(Site.region_slug == region)
    sites = session.scalars(statement).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "project_code",
            "jurisdiction",
            "county",
            "site_kind",
            "site_kind_assertion",
            "current_stage",
            "current_stage_label",
            "confidence_percent",
            "total_acres",
            "evidence_count",
            "first_signal_date",
            "latest_signal_date",
            "operator_status",
            "score_last_calculated_at",
        ]
    )
    for site in sites:
        writer.writerow(
            [
                site.project_code,
                site.jurisdiction or "",
                site.county,
                site.site_kind,
                site.site_kind_assertion,
                site.current_stage,
                DevelopmentStage(site.current_stage).label,
                round(site.current_confidence, 2),
                float(site.total_acres) if site.total_acres is not None else "",
                site.evidence_count,
                site.first_signal_date.isoformat() if site.first_signal_date else "",
                site.latest_signal_date.isoformat() if site.latest_signal_date else "",
                "not_established" if site.operator_organization_id is None else "asserted",
                (
                    site.score_last_calculated_at.isoformat()
                    if site.score_last_calculated_at
                    else ""
                ),
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="helios-sites.csv"'},
    )


@router.get("/sites.geojson", summary="Export sites as GeoJSON")
def export_sites_geojson(
    session: DbSession,
    region: Annotated[str | None, Query()] = None,
) -> Response:
    """Export site boundaries as a GeoJSON FeatureCollection."""
    statement = select(Site).where(Site.boundary.isnot(None))
    if region:
        statement = statement.where(Site.region_slug == region)
    sites = session.scalars(statement).all()

    attributions = sorted(
        {
            text
            for text in session.scalars(
                select(Source.attribution_text).where(Source.attribution_required.is_(True))
            ).all()
            if text
        }
    )

    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "generator": "Project Helios",
            "generated_at": utcnow().isoformat(),
            "attributions": attributions,
            "disclaimer": DISCLAIMER,
        },
        "features": [
            {
                "type": "Feature",
                "geometry": geometry_to_geojson(site.boundary),
                "properties": {
                    "project_code": site.project_code,
                    "jurisdiction": site.jurisdiction,
                    "site_kind": site.site_kind,
                    "site_kind_assertion": site.site_kind_assertion,
                    "stage": site.current_stage,
                    "stage_label": DevelopmentStage(site.current_stage).label,
                    "confidence": round(site.current_confidence, 2),
                    "total_acres": (
                        float(site.total_acres) if site.total_acres is not None else None
                    ),
                    "evidence_count": site.evidence_count,
                },
            }
            for site in sites
        ],
    }

    return Response(
        content=json.dumps(collection, indent=2),
        media_type="application/geo+json",
        headers={"Content-Disposition": 'attachment; filename="helios-sites.geojson"'},
    )


def _build_evidence_payload(session: DbSession, site: Site) -> dict:
    """Assemble the machine-readable evidence record for a site."""
    evidence = session.scalars(
        select(EvidenceRecord)
        .where(EvidenceRecord.site_id == site.id)
        .order_by(EvidenceRecord.observed_at)
    ).all()

    predictions = session.scalars(
        select(Prediction).where(Prediction.site_id == site.id).order_by(Prediction.calculated_at)
    ).all()

    history = session.scalars(
        select(SiteStageHistory)
        .where(SiteStageHistory.site_id == site.id)
        .order_by(SiteStageHistory.effective_date)
    ).all()

    return {
        "generated_at": utcnow().isoformat(),
        "generator": "Project Helios",
        "disclaimer": DISCLAIMER,
        "site": {
            "project_code": site.project_code,
            "jurisdiction": site.jurisdiction,
            "county": site.county,
            "site_kind": site.site_kind,
            "site_kind_assertion": site.site_kind_assertion,
            "current_stage": site.current_stage,
            "current_stage_label": DevelopmentStage(site.current_stage).label,
            "current_confidence": round(site.current_confidence, 2),
            "total_acres": float(site.total_acres) if site.total_acres is not None else None,
            "first_signal_date": (
                site.first_signal_date.isoformat() if site.first_signal_date else None
            ),
            "latest_signal_date": (
                site.latest_signal_date.isoformat() if site.latest_signal_date else None
            ),
            "operator_status": (
                "not_established" if site.operator_organization_id is None else "asserted"
            ),
            "summary": site.summary,
            "boundary": geometry_to_geojson(site.boundary),
        },
        "evidence": [
            json.loads(serialize_evidence(session, record).model_dump_json()) for record in evidence
        ],
        "stage_history": [
            json.loads(serialize_stage_transition(h).model_dump_json()) for h in history
        ],
        "predictions": [
            json.loads(serialize_prediction(session, p).model_dump_json()) for p in predictions
        ],
        "scoring_model": {
            "name": SCORING_MODEL_NAME,
            "version": SCORING_MODEL_VERSION,
            "parameters_hash": model_parameters_hash(),
            "parameters": model_parameters(),
        },
        "attributions": collect_attributions(session, site.id),
    }


@router.get(
    "/site/{site_id}/evidence.json",
    summary="Export a site's evidence with full provenance",
)
def export_site_evidence(session: DbSession, site_id: UUID) -> Response:
    """Export every evidence record for a site as JSON."""
    site = _get_site_or_404(session, site_id)
    payload = _build_evidence_payload(session, site)
    return Response(
        content=json.dumps(payload, indent=2, default=str),
        media_type="application/json",
        headers={
            "Content-Disposition": (f'attachment; filename="{site.project_code}-evidence.json"')
        },
    )


@router.get(
    "/site/{site_id}/bundle.zip",
    summary="Download a complete, verifiable evidence bundle",
)
def export_site_bundle(session: DbSession, site_id: UUID) -> Response:
    """Build a reproducibility bundle for one site.

    The bundle is designed so a sceptical reader can verify Helios without
    trusting it: ``manifest.json`` lists the SHA-256 of every source document
    behind the conclusion, so the originals can be re-fetched and re-hashed.
    """
    site = _get_site_or_404(session, site_id)
    payload = _build_evidence_payload(session, site)

    parcels = session.execute(
        select(Parcel, SiteParcelLink)
        .join(SiteParcelLink, SiteParcelLink.parcel_id == Parcel.id)
        .where(SiteParcelLink.site_id == site.id)
    ).all()

    documents = session.execute(
        select(SourceDocument, Source)
        .join(Source, Source.id == SourceDocument.source_id)
        .join(EvidenceRecord, EvidenceRecord.document_id == SourceDocument.id)
        .where(EvidenceRecord.site_id == site.id)
        .distinct()
    ).all()

    manifest_documents = []
    for document, source in documents:
        versions = session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number)
        ).all()
        manifest_documents.append(
            {
                "document_id": str(document.id),
                "source_slug": source.slug,
                "source_name": source.name,
                "agency": source.agency,
                "source_native_id": document.source_native_id,
                "source_url": document.source_url,
                "licence": source.license_name,
                "attribution_required": source.attribution_required,
                "versions": [
                    {
                        "version_number": v.version_number,
                        "content_sha256": v.content_sha256,
                        "content_length": v.content_length,
                        "mime_type": v.mime_type,
                        "retrieved_at": v.retrieved_at.isoformat(),
                        "storage_key": v.storage_key,
                        "parser_version": v.parser_version,
                    }
                    for v in versions
                ],
            }
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("evidence.json", json.dumps(payload, indent=2, default=str))
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "bundle_version": "1.0",
                    "generated_at": utcnow().isoformat(),
                    "project_code": site.project_code,
                    "verification": (
                        "Re-fetch each source_url and compare the SHA-256 of the response "
                        "against content_sha256 below. Content may have changed upstream "
                        "since retrieval; Helios retains the original bytes it hashed."
                    ),
                    "documents": manifest_documents,
                },
                indent=2,
            ),
        )

        parcel_csv = io.StringIO()
        writer = csv.writer(parcel_csv)
        writer.writerow(
            [
                "apn",
                "situs_address",
                "situs_city",
                "owner_name",
                "owner_is_redacted",
                "land_use_description",
                "lot_size_acres",
                "last_deed_date",
                "last_deed_number",
                "last_deed_url",
                "link_reason",
                "link_confidence",
            ]
        )
        for parcel, link in parcels:
            writer.writerow(
                [
                    parcel.apn,
                    parcel.situs_address or "",
                    parcel.situs_city or "",
                    "" if parcel.owner_is_redacted else (parcel.owner_name_raw or ""),
                    parcel.owner_is_redacted,
                    parcel.land_use_description or "",
                    float(parcel.lot_size_acres) if parcel.lot_size_acres is not None else "",
                    parcel.last_deed_date.isoformat() if parcel.last_deed_date else "",
                    parcel.last_deed_number or "",
                    parcel.last_deed_url or "",
                    link.link_reason,
                    link.confidence,
                ]
            )
        archive.writestr("parcels.csv", parcel_csv.getvalue())

        boundary = geometry_to_geojson(site.boundary)
        if boundary:
            archive.writestr(
                "site.geojson",
                json.dumps(
                    {
                        "type": "Feature",
                        "geometry": boundary,
                        "properties": {"project_code": site.project_code},
                    },
                    indent=2,
                ),
            )

        archive.writestr("README.txt", _bundle_readme(site, payload))

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{site.project_code}-bundle.zip"'},
    )


def _bundle_readme(site: Site, payload: dict) -> str:
    """Compose the human-readable explanation shipped inside a bundle."""
    attributions = "\n".join(f"  - {a}" for a in payload["attributions"]) or "  (none)"
    return f"""Helios Evidence Bundle
======================

Project code : {site.project_code}
Jurisdiction : {site.jurisdiction or "unknown"}
Generated    : {datetime.now(tz=UTC).isoformat()}

Contents
--------
  evidence.json   Site profile, every evidence record with provenance, stage
                  history, and every recorded prediction with its explanation.
  manifest.json   SHA-256 of each source document behind this conclusion.
  parcels.csv     Parcels linked to this site and why each was linked.
  site.geojson    Site boundary geometry (WGS 84).

How to verify this bundle
-------------------------
1. Open manifest.json and take any document's source_url.
2. Re-fetch it and compute the SHA-256 of the response body.
3. Compare against content_sha256. A mismatch means the source changed after
   Helios retrieved it, not that Helios recorded it incorrectly - Helios keeps
   the original bytes it hashed.
4. Every evidence record in evidence.json names the document version it came
   from and the locator within it, so each individual claim is checkable.

Interpretation
--------------
{DISCLAIMER}

Current stage      : {payload["site"]["current_stage_label"]}
Current confidence : {payload["site"]["current_confidence"]}%
Operator           : {payload["site"]["operator_status"]}

Attributions
------------
{attributions}
"""


__all__ = ["router"]
