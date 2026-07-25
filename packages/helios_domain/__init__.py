"""The Helios domain layer: ontology, persistence models, and session management.

This package knows nothing about HTTP, React, or any specific data source. It
defines *what exists* in the Helios world and how those things are stored, so
that connectors, scoring, and the API all agree on one vocabulary.
"""

from helios_domain.base import Base
from helios_domain.ontology import (
    DevelopmentStage,
    OrganizationRelationshipType,
    OrganizationRole,
    PermitCategory,
    SiteRelationType,
    StageEvidenceKind,
)
from helios_domain.session import (
    create_engine_from_settings,
    get_session,
    session_scope,
)

__all__ = [
    "Base",
    "DevelopmentStage",
    "OrganizationRelationshipType",
    "OrganizationRole",
    "PermitCategory",
    "SiteRelationType",
    "StageEvidenceKind",
    "create_engine_from_settings",
    "get_session",
    "session_scope",
]
