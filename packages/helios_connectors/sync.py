"""Synchronise the declarative source registry into the database.

The registry in :mod:`helios_connectors.registry` is the authoritative,
version-controlled description of what Helios is allowed to read. This module
projects it into the ``sources`` and ``source_connectors`` tables so the API can
serve it and connector runs can reference it.

Synchronisation is idempotent and additive: it updates declared attributes and
never deletes rows, because a source row may be referenced by documents that
must remain citable even after the source is retired.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from helios_common.logging import get_logger
from helios_connectors.registry import SOURCE_REGISTRY, SourceRegistryEntry
from helios_domain.models import Source, SourceConnector

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger(__name__)


def sync_source(session: Session, entry: SourceRegistryEntry) -> Source:
    """Create or update the ``sources`` row for one registry entry.

    Args:
        session: Open database session.
        entry: Declarative registry entry.

    Returns:
        The persisted source row (not yet committed).
    """
    source = session.scalar(select(Source).where(Source.slug == entry.slug))
    if source is None:
        source = Source(slug=entry.slug)
        session.add(source)

    source.name = entry.name
    source.agency = entry.agency
    source.jurisdiction = entry.jurisdiction
    source.category = str(entry.category)
    source.base_url = entry.base_url
    source.access_method = str(entry.access_method)
    source.update_frequency = entry.update_frequency
    source.requires_authentication = entry.requires_authentication
    source.authentication_notes = entry.authentication_notes
    source.rate_limit_per_second = entry.rate_limit_per_second
    source.rate_limit_notes = entry.rate_limit_notes
    source.license_name = entry.license_name
    source.license_url = entry.license_url
    source.licensing_notes = entry.licensing_notes
    source.attribution_required = entry.attribution_required
    source.attribution_text = entry.attribution_text
    source.robots_policy_status = entry.robots_policy_status
    source.terms_of_service_url = entry.terms_of_service_url
    source.geographic_coverage = entry.geographic_coverage
    source.historical_coverage = entry.historical_coverage
    source.contains_personal_data = entry.contains_personal_data
    source.reliability_score = entry.reliability_score
    source.known_schema_issues = entry.known_schema_issues
    source.notes = entry.notes

    # Set on every source, not only the ones with a connector: a source with no
    # connector is precisely the case where the reader needs to be told why.
    source.connector_status = str(entry.connector_status)
    source.access_limitation = entry.access_limitation

    if entry.connector_slug and entry.connector_entry_point:
        _sync_connector(session, source, entry)

    return source


def _sync_connector(
    session: Session, source: Source, entry: SourceRegistryEntry
) -> SourceConnector:
    """Create or update the ``source_connectors`` row for a registry entry."""
    connector = session.scalar(
        select(SourceConnector).where(SourceConnector.slug == entry.connector_slug)
    )
    if connector is None:
        connector = SourceConnector(slug=entry.connector_slug or entry.slug)
        session.add(connector)

    connector.source = source
    connector.entry_point = entry.connector_entry_point or ""
    connector.status = str(entry.connector_status)
    connector.access_limitation = entry.access_limitation
    return connector


def sync_registry(session: Session) -> dict[str, int]:
    """Project the whole registry into the database.

    Args:
        session: Open database session.

    Returns:
        Counts of sources and connectors synchronised.
    """
    connector_count = 0
    for entry in SOURCE_REGISTRY:
        sync_source(session, entry)
        if entry.connector_slug:
            connector_count += 1
    session.flush()

    logger.info("registry.synced", sources=len(SOURCE_REGISTRY), connectors=connector_count)
    return {"sources": len(SOURCE_REGISTRY), "connectors": connector_count}


__all__ = ["sync_registry", "sync_source"]
