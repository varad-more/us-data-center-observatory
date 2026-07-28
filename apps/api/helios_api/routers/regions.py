"""Region-registry endpoint.

Sibling to ``/sources``, and for the same reason. That endpoint publishes which
*sources* Helios can read; this one publishes which *places*. A registry that
listed only the region Helios reads would say nothing about the shape of the
gap, and a registry that listed intended regions without marking them would
imply a coverage that does not exist. So each region carries its coverage
status and the number of sites actually held there — which, for everywhere
except the pilot region, is zero.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from helios_api.deps import DbSession
from helios_api.schemas import RegionListResponse, RegionResponse
from helios_domain.models import Site
from helios_domain.regions import REGIONS, RegionCoverage

router = APIRouter(tags=["regions"])

_NOTE = (
    "Helios names more regions than it reads. A region listed as 'declared' is "
    "in scope and holds no data; only 'active' regions have connectors behind "
    "them. Site counts are the check on that claim."
)


@router.get("/regions", response_model=RegionListResponse, summary="The region registry")
def list_regions(session: DbSession) -> RegionListResponse:
    """Return every registered region with its coverage status and site count."""
    counts: dict[str, int] = {}
    for slug, count in session.execute(
        select(Site.region_slug, func.count()).group_by(Site.region_slug)
    ):
        counts[slug] = count

    items = [
        RegionResponse(
            slug=region.slug,
            name=region.name,
            state_code=region.state_code,
            coverage=str(region.coverage),
            counties=list(region.counties),
            cities=list(region.cities),
            bbox=list(region.bbox),
            note=region.note,
            site_count=int(counts.get(region.slug, 0)),
        )
        for region in REGIONS
    ]

    return RegionListResponse(
        items=items,
        active_count=sum(1 for r in REGIONS if r.coverage is RegionCoverage.ACTIVE),
        declared_count=sum(1 for r in REGIONS if r.coverage is RegionCoverage.DECLARED),
        note=_NOTE,
    )
