"""The Helios domain ontology.

Defines the controlled vocabularies that describe the *world* Helios models, as
distinct from :mod:`helios_common.vocabulary`, which describes how confident
Helios is about what it knows.

The centrepiece is :class:`DevelopmentStage`, an ordered state machine tracking a
site from "nothing is happening here" through to "operating and expanding".
Stages are deliberately coarse: public records are lumpy, and a finer model would
imply a resolution the evidence cannot support.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class DevelopmentStage(IntEnum):
    """Ordered development stages for a suspected data-center site.

    Integer-valued so that progression and regression are simple comparisons and
    so that ordering survives a round trip through the database. A site may move
    forward, hold, or be **downgraded** when evidence is contradicted - the model
    is not monotonic, and every transition is retained in ``site_stage_history``.
    """

    NO_KNOWN_DEVELOPMENT = 0
    SITE_SPECULATION = 1
    INFRASTRUCTURE_INTENT = 2
    REGULATORY_COMMITMENT = 3
    CONSTRUCTION_INITIATED = 4
    STRUCTURAL_BUILDOUT = 5
    ENERGIZATION = 6
    OPERATIONAL = 7
    EXPANSION = 8

    @property
    def label(self) -> str:
        """Human-readable stage name for display."""
        return _STAGE_LABELS[self]

    @property
    def description(self) -> str:
        """One-sentence description of what this stage means."""
        return _STAGE_DESCRIPTIONS[self]

    @classmethod
    def from_value(cls, value: int | str | DevelopmentStage) -> DevelopmentStage:
        """Coerce an int, name, or member into a stage.

        Args:
            value: Stage ordinal, member name (case-insensitive), or member.

        Returns:
            The matching stage.

        Raises:
            ValueError: If the value matches no stage.
        """
        if isinstance(value, DevelopmentStage):
            return value
        if isinstance(value, int):
            return cls(value)
        key = value.strip().upper().replace("-", "_").replace(" ", "_")
        try:
            return cls[key]
        except KeyError as exc:
            raise ValueError(f"Unknown development stage: {value!r}") from exc


_STAGE_LABELS: dict[DevelopmentStage, str] = {
    DevelopmentStage.NO_KNOWN_DEVELOPMENT: "No known development",
    DevelopmentStage.SITE_SPECULATION: "Site speculation",
    DevelopmentStage.INFRASTRUCTURE_INTENT: "Infrastructure intent",
    DevelopmentStage.REGULATORY_COMMITMENT: "Regulatory commitment",
    DevelopmentStage.CONSTRUCTION_INITIATED: "Construction initiated",
    DevelopmentStage.STRUCTURAL_BUILDOUT: "Structural buildout",
    DevelopmentStage.ENERGIZATION: "Energization",
    DevelopmentStage.OPERATIONAL: "Operational",
    DevelopmentStage.EXPANSION: "Expansion",
}

_STAGE_DESCRIPTIONS: dict[DevelopmentStage, str] = {
    DevelopmentStage.NO_KNOWN_DEVELOPMENT: (
        "An industrial or vacant parcel exists but no meaningful project evidence has been found."
    ),
    DevelopmentStage.SITE_SPECULATION: (
        "Land-market activity consistent with assembly for a large project: bulk purchases, "
        "adjacent-parcel consolidation, or a newly formed single-purpose entity taking title."
    ),
    DevelopmentStage.INFRASTRUCTURE_INTENT: (
        "A party has formally asked a public body for something a large facility would need: "
        "rezoning, a planning application, a utility service inquiry, or a development agreement."
    ),
    DevelopmentStage.REGULATORY_COMMITMENT: (
        "Permits or filings have been submitted that are expensive to abandon: air, water, "
        "stormwater, generator, transmission, or substation applications."
    ),
    DevelopmentStage.CONSTRUCTION_INITIATED: (
        "Ground disturbance has begun: grading permits, dust-control registrations, "
        "construction roads, or observed earth-moving."
    ),
    DevelopmentStage.STRUCTURAL_BUILDOUT: (
        "Vertical construction is visible: foundations, roof structures, generator yards, "
        "cooling plant, or substation equipment installation."
    ),
    DevelopmentStage.ENERGIZATION: (
        "Grid connection is being completed: substation energization, transmission completion, "
        "electrical inspection sign-off, or first recorded load."
    ),
    DevelopmentStage.OPERATIONAL: (
        "The facility is in service: occupancy approval, sustained load, hiring, or an operator "
        "confirmation."
    ),
    DevelopmentStage.EXPANSION: (
        "An operating campus is growing: further parcel acquisition, additional phases, "
        "more generators, or increased requested utility capacity."
    ),
}


class StageEvidenceKind(StrEnum):
    """Categories of evidence that bear on stage classification and scoring.

    These are the units the rule-based confidence model reasons over. Keeping
    them as an enum (rather than free text) means a scoring rule can never
    silently stop matching because a connector spelled a category differently.
    """

    # --- land ---
    LARGE_INDUSTRIAL_PARCEL_ACQUISITION = "large_industrial_parcel_acquisition"
    ADJACENT_PARCEL_CONSOLIDATION = "adjacent_parcel_consolidation"
    SHELL_ENTITY_OWNERSHIP = "shell_entity_ownership"
    KNOWN_DEVELOPER_RELATIONSHIP = "known_developer_relationship"

    # --- planning ---
    ZONING_REQUEST = "zoning_request"
    PLANNING_APPLICATION_DATA_CENTER = "planning_application_data_center"
    DEVELOPMENT_AGREEMENT = "development_agreement"
    DATA_CENTER_COMPATIBLE_ZONING = "data_center_compatible_zoning"
    ASSESSOR_DATA_CENTER_CLASSIFICATION = "assessor_data_center_classification"

    # --- utility ---
    UTILITY_SERVICE_INQUIRY = "utility_service_inquiry"
    TRANSMISSION_FILING = "transmission_filing"
    SUBSTATION_APPLICATION = "substation_application"
    DEDICATED_SUBSTATION_PROXIMITY = "dedicated_substation_proximity"
    HIGH_VOLTAGE_TRANSMISSION_PROXIMITY = "high_voltage_transmission_proximity"

    # --- environmental ---
    BACKUP_GENERATOR_AIR_PERMIT = "backup_generator_air_permit"
    AIR_PERMIT = "air_permit"
    WATER_OR_COOLING_PERMIT = "water_or_cooling_permit"
    STORMWATER_PERMIT = "stormwater_permit"

    # --- construction ---
    GRADING_OR_CONSTRUCTION_PERMIT = "grading_or_construction_permit"
    DUST_CONTROL_REGISTRATION = "dust_control_registration"
    SATELLITE_CONSTRUCTION_CHANGE = "satellite_construction_change"

    # --- operation ---
    HIRING_OR_PROCUREMENT_SIGNAL = "hiring_or_procurement_signal"
    OCCUPANCY_APPROVAL = "occupancy_approval"
    OPERATOR_ANNOUNCEMENT = "operator_announcement"

    # --- negative ---
    CONFLICTING_FACILITY_CLASSIFICATION = "conflicting_facility_classification"
    PROJECT_CANCELLATION = "project_cancellation"
    STALE_EVIDENCE_NO_PROGRESSION = "stale_evidence_no_progression"


class OrganizationRole(StrEnum):
    """The function an organization plays with respect to a site."""

    UNKNOWN = "unknown"
    OWNER = "owner"
    OPERATOR = "operator"
    DEVELOPER = "developer"
    CONTRACTOR = "contractor"
    UTILITY = "utility"
    WATER_PROVIDER = "water_provider"
    SHELL_COMPANY = "shell_company"
    PARENT_COMPANY = "parent_company"
    REGISTERED_AGENT = "registered_agent"
    GOVERNMENT_BODY = "government_body"
    NATURAL_PERSON = "natural_person"
    """Retained as a classification so PII can be filtered, never to profile individuals."""


class OrganizationRelationshipType(StrEnum):
    """Typed, time-bounded edges between organizations."""

    PARENT_OF = "PARENT_OF"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    REGISTERED_AGENT_FOR = "REGISTERED_AGENT_FOR"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    DEVELOPED_BY = "DEVELOPED_BY"
    CONTRACTED_BY = "CONTRACTED_BY"
    SHARES_MAILING_ADDRESS = "SHARES_MAILING_ADDRESS"
    ALIAS_OF = "ALIAS_OF"


class SiteRelationType(StrEnum):
    """Relationships between a site and other domain objects."""

    LOCATED_ON = "LOCATED_ON"
    ADJACENT_TO = "ADJACENT_TO"
    SERVED_BY = "SERVED_BY"
    POWERED_BY = "POWERED_BY"
    CONNECTED_TO = "CONNECTED_TO"
    DEPENDS_ON = "DEPENDS_ON"
    EXPANDS = "EXPANDS"
    REPLACES = "REPLACES"


class EvidenceRelationType(StrEnum):
    """How one evidence record relates to another."""

    SUPPORTS = "SUPPORTED_BY"
    CONFIRMS = "CONFIRMS"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"
    MENTIONED_IN = "MENTIONED_IN"
    REPLACES = "REPLACES"


class PermitCategory(StrEnum):
    """Normalised permit taxonomy across jurisdictions.

    Municipalities each invent their own permit-type strings; connectors map
    those onto this shared set so scoring rules stay jurisdiction-agnostic.
    """

    UNKNOWN = "unknown"
    AIR_QUALITY = "air_quality"
    BACKUP_GENERATOR = "backup_generator"
    WATER = "water"
    WASTEWATER = "wastewater"
    STORMWATER = "stormwater"
    GRADING = "grading"
    DUST_CONTROL = "dust_control"
    BUILDING_COMMERCIAL = "building_commercial"
    BUILDING_RESIDENTIAL = "building_residential"
    ELECTRICAL = "electrical"
    OCCUPANCY = "occupancy"
    SITE_PLAN = "site_plan"
    ZONING = "zoning"
    RIGHT_OF_WAY = "right_of_way"


class InfrastructureKind(StrEnum):
    """Types of physical infrastructure a site can depend on."""

    SUBSTATION = "substation"
    TRANSMISSION_LINE = "transmission_line"
    GENERATION = "generation"
    WATER_CONNECTION = "water_connection"
    WASTEWATER_CONNECTION = "wastewater_connection"
    FIBER_CORRIDOR = "fiber_corridor"
    ROAD_IMPROVEMENT = "road_improvement"


class SiteKind(StrEnum):
    """What Helios believes a site is, always paired with an assertion class."""

    UNKNOWN = "unknown"
    SUSPECTED_DATA_CENTER = "suspected_data_center"
    HYPERSCALE_CAMPUS = "hyperscale_campus"
    COLOCATION_FACILITY = "colocation_facility"
    ENTERPRISE_DATA_CENTER = "enterprise_data_center"
    NETWORK_FACILITY = "network_facility"
    NOT_A_DATA_CENTER = "not_a_data_center"


__all__ = [
    "DevelopmentStage",
    "EvidenceRelationType",
    "InfrastructureKind",
    "OrganizationRelationshipType",
    "OrganizationRole",
    "PermitCategory",
    "SiteKind",
    "SiteRelationType",
    "StageEvidenceKind",
]
