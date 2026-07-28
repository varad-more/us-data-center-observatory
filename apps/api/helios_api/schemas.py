"""Pydantic response models for the Helios API.

Two conventions run through every schema and are the API's contribution to the
product's honesty requirements:

* Anything Helios concluded rather than read is accompanied by an
  ``assertion_class``, so a client cannot render an inference as a fact without
  actively discarding information.
* Nullable fields mean "not established", never zero. A site with unknown power
  demand returns ``null``, never ``0``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HeliosModel(BaseModel):
    """Base model with shared configuration."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ------------------------------------------------------------------ health --


class HealthResponse(HeliosModel):
    """Liveness response."""

    status: str
    version: str
    environment: str


class ReadinessResponse(HeliosModel):
    """Readiness response, including dependency checks."""

    ready: bool
    checks: dict[str, str]


# ----------------------------------------------------------------- paging --


class PageMeta(HeliosModel):
    """Pagination metadata."""

    total: int
    limit: int
    offset: int
    has_more: bool


# ------------------------------------------------------------------ sites --


class AssertedValue(HeliosModel):
    """A value paired with how it was established.

    Used wherever a client might otherwise mistake an inference for a reading.
    """

    value: Any = None
    assertion_class: str = Field(
        description="reported | extracted | calculated | inferred | predicted | unknown"
    )
    detail: str | None = None


class SiteSummary(HeliosModel):
    """A site as it appears in lists and on the map."""

    id: UUID
    project_code: str
    display_name: str | None
    site_kind: str
    site_kind_assertion: str
    jurisdiction: str | None
    county: str
    region_slug: str

    current_stage: int
    current_stage_label: str
    current_confidence: float
    stage_confidence: float
    confidence_band: str

    first_signal_date: date | None
    latest_signal_date: date | None
    evidence_count: int
    total_acres: float | None
    parcel_count: int

    operator_status: str = Field(
        description=(
            "Almost always 'not_established'. Helios does not name an operator "
            "without a direct filing."
        )
    )
    stage_last_changed_at: datetime | None
    score_last_calculated_at: datetime | None
    centroid: list[float] | None = Field(default=None, description="[longitude, latitude]")
    is_synthetic: bool


class ParcelSummary(HeliosModel):
    """A parcel linked to a site."""

    id: UUID
    apn: str
    apn_formatted: str | None
    situs_address: str | None
    situs_city: str | None
    owner_name: str | None = Field(
        description="Null when the owner was classified as a private individual and redacted."
    )
    owner_is_redacted: bool
    land_use_description: str | None
    lot_size_acres: float | None
    last_deed_date: date | None
    last_deed_number: str | None
    last_deed_url: str | None
    last_sale_price: float | None
    assessor_url: str | None
    link_reason: str | None = None
    link_confidence: float | None = None


class OrganizationSummary(HeliosModel):
    """An organization associated with a site."""

    id: UUID
    canonical_name: str
    role: str
    organization_type: str | None
    is_suspected_shell: bool
    shell_indicators: list[str]
    mailing_city: str | None
    mailing_state: str | None
    attribution_note: str = Field(
        default=(
            "Helios records the entity of record only. Shell-company indicators are "
            "flags for human review and do not constitute an attribution to any parent."
        )
    )


class SourceReference(HeliosModel):
    """Provenance pointer accompanying a piece of evidence."""

    document_id: UUID
    document_version_id: UUID
    source_slug: str
    source_name: str
    agency: str
    source_url: str
    retrieved_at: datetime
    content_sha256: str
    parser_version: str | None
    attribution_text: str | None


class EvidenceItemResponse(HeliosModel):
    """One cited fact on a site's timeline."""

    id: UUID
    evidence_kind: str
    summary: str
    snippet: str | None
    snippet_locator: str | None
    observed_at: date
    assertion_class: str
    extraction_method: str
    polarity: str
    confidence: float
    human_review_status: str
    is_standing_condition: bool
    normalized_values: dict[str, Any]
    source: SourceReference


class StageTransition(HeliosModel):
    """A recorded change in a site's development stage."""

    id: UUID
    from_stage: int | None
    from_stage_label: str | None
    to_stage: int
    to_stage_label: str
    effective_date: date
    detected_at: datetime
    is_downgrade: bool
    confidence: float
    rationale: str
    triggering_evidence_ids: list[str]
    detection_lag_days: int | None = Field(
        default=None,
        description=(
            "Days between when the transition took effect and when Helios detected it. "
            "Large values indicate the evidence predated ingestion."
        ),
    )


class TimelineEntry(HeliosModel):
    """A unified chronological entry combining evidence and stage changes."""

    entry_type: str = Field(description="evidence | stage_transition | score_change")
    occurred_on: date
    title: str
    detail: str
    evidence: EvidenceItemResponse | None = None
    stage_transition: StageTransition | None = None
    confidence_delta: float | None = None


class ScoreExplanation(HeliosModel):
    """One rule contribution to a confidence score."""

    rule_id: str
    evidence_kind: str | None
    label: str
    detail: str | None
    base_weight: float
    applied_weight: float
    confidence_multiplier: float
    recency_multiplier: float
    polarity: str
    evidence_record_id: UUID | None


class PredictionResponse(HeliosModel):
    """A scored prediction with its full explanation."""

    id: UUID
    calculated_at: datetime
    as_of_date: date
    predicted_stage: int | None
    predicted_stage_label: str | None
    raw_score: float
    confidence: float
    confidence_band: str
    positive_contribution: float
    negative_contribution: float
    evidence_considered: int
    distinct_evidence_kinds: int
    is_backtest: bool
    summary: str | None
    model_name: str
    model_version: str
    explanations: list[ScoreExplanation]


class DependencyResponse(HeliosModel):
    """An infrastructure dependency edge."""

    id: UUID
    infrastructure_kind: str
    label: str
    dependency_status: str
    is_blocking: bool
    match_method: str | None
    distance_meters: float | None
    confidence: float
    assertion_class: str
    notes: str | None
    voltage_kv: float | None = None
    operator_name: str | None = None


class EstimateResponse(HeliosModel):
    """A ranged estimate with its method and assumptions."""

    id: UUID
    estimate_type: str
    unit: str
    lower_value: float | None
    likely_value: float | None
    upper_value: float | None
    method: str
    assertion_class: str
    confidence: float
    assumptions: dict[str, Any]
    calculated_at: datetime
    notes: str | None


class SiteDetail(SiteSummary):
    """Full site profile."""

    summary: str | None
    boundary: dict[str, Any] | None = Field(default=None, description="GeoJSON geometry")
    parcels: list[ParcelSummary]
    organizations: list[OrganizationSummary]
    dependencies: list[DependencyResponse]
    estimates: list[EstimateResponse]
    latest_prediction: PredictionResponse | None
    stage_history: list[StageTransition]
    attributions: list[str] = Field(
        default_factory=list,
        description="Licence attributions required by the sources behind this profile.",
    )


class SiteListResponse(HeliosModel):
    """Paged list of sites."""

    items: list[SiteSummary]
    meta: PageMeta


class EvidenceListResponse(HeliosModel):
    """Paged list of evidence records."""

    items: list[EvidenceItemResponse]
    meta: PageMeta


class TimelineResponse(HeliosModel):
    """A site's chronological narrative."""

    site_id: UUID
    project_code: str
    entries: list[TimelineEntry]
    first_signal_date: date | None
    latest_signal_date: date | None


class ScoreHistoryResponse(HeliosModel):
    """How a site's score changed over time."""

    site_id: UUID
    project_code: str
    predictions: list[PredictionResponse]


# ------------------------------------------------------------------- map ----


class MapFeatureCollection(HeliosModel):
    """A GeoJSON FeatureCollection."""

    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    attributions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------- sources ----


class SourceResponse(HeliosModel):
    """A source-registry entry as served by the API."""

    id: UUID
    slug: str
    name: str
    agency: str
    jurisdiction: str
    category: str
    base_url: str
    access_method: str
    update_frequency: str | None
    license_name: str | None
    license_url: str | None
    attribution_required: bool
    attribution_text: str | None
    robots_policy_status: str | None
    geographic_coverage: str | None
    historical_coverage: str | None
    contains_personal_data: bool
    reliability_score: float | None
    known_schema_issues: str | None
    notes: str | None
    connector_status: str | None
    connector_slug: str | None
    access_limitation: str | None
    last_success_at: datetime | None
    document_count: int


class SourceListResponse(HeliosModel):
    """The full source registry."""

    items: list[SourceResponse]
    coverage_summary: dict[str, int]


class ConnectorRunResponse(HeliosModel):
    """Telemetry for one connector run."""

    id: UUID
    connector_slug: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    status: str
    mode: str
    items_discovered: int
    items_fetched: int
    items_parsed: int
    items_normalized: int
    items_rejected: int
    items_unchanged: int
    versions_created: int
    evidence_created: int
    schema_drift_detected: bool
    message: str | None


# -------------------------------------------------------------- documents ---


class DocumentVersionResponse(HeliosModel):
    """One immutable snapshot of a document."""

    id: UUID
    version_number: int
    content_sha256: str
    content_length: int
    mime_type: str
    retrieved_at: datetime
    source_url: str
    http_status: int | None
    etag: str | None
    connector_version: str | None
    parser_version: str | None
    supersedes_version_id: UUID | None


class DocumentResponse(HeliosModel):
    """A source document and its version history."""

    id: UUID
    source_slug: str
    source_name: str
    source_native_id: str
    title: str | None
    document_type: str | None
    source_url: str
    published_date: date | None
    effective_date: date | None
    first_seen_at: datetime
    last_seen_at: datetime
    version_count: int
    is_synthetic: bool
    versions: list[DocumentVersionResponse]


# -------------------------------------------------------------- analytics ---


class StageDistributionEntry(HeliosModel):
    """Count of sites at one development stage."""

    stage: int
    stage_label: str
    site_count: int
    mean_confidence: float | None


class AnalyticsStagesResponse(HeliosModel):
    """Distribution of sites across stages."""

    region_slug: str | None
    total_sites: int
    stages: list[StageDistributionEntry]


class StageGrowthPoint(HeliosModel):
    """How many sites had reached each stage as of one month."""

    month: str
    """Month bucket as ``YYYY-MM``."""

    cumulative_by_stage: dict[int, int]
    """Stage -> count of sites that had reached *at least* that stage."""

    sites_tracked: int
    """Distinct sites with any recorded transition by this month."""


class StageGrowthResponse(HeliosModel):
    """Development activity over time, derived from recorded stage transitions."""

    region_slug: str | None
    points: list[StageGrowthPoint]
    note: str


class DetectionLagEntry(HeliosModel):
    """One stage transition and how long Helios took to notice it."""

    project_code: str
    to_stage: int
    stage_label: str
    effective_date: date
    detected_at: datetime
    lag_days: int
    """``detected_at`` minus ``effective_date``. Negative means Helios recorded
    the transition before the effective date it later attributed to it."""


class DetectionLagResponse(HeliosModel):
    """Measured detection lag across all recorded transitions.

    Helios claims to be an early-warning system. This is that claim rendered as a
    measurement rather than an assertion.
    """

    region_slug: str | None
    transitions: int
    median_lag_days: float | None
    p90_lag_days: float | None
    min_lag_days: int | None
    max_lag_days: int | None
    slowest: list[DetectionLagEntry]
    note: str


class ProvenanceCompletenessResponse(HeliosModel):
    """Measured provenance completeness across all evidence."""

    total_evidence_records: int
    with_document_version: int
    with_snippet: int
    with_locator: int
    with_observation_date: int
    completeness_ratio: float
    note: str


class RegionResponse(HeliosModel):
    """One registered region and how much of it Helios actually reads."""

    slug: str
    name: str
    state_code: str
    coverage: str
    """``active`` if a connector reads it, ``declared`` if it is only named."""

    counties: list[str]
    cities: list[str]
    bbox: list[float]
    note: str
    site_count: int
    """Sites Helios holds here. Always zero for a declared region."""


class RegionListResponse(HeliosModel):
    """The region registry, with the coverage gap stated rather than implied.

    A region appearing here is not a claim that Helios is watching it. Naming
    where the project intends to go is useful; letting that read as coverage
    would not be.
    """

    items: list[RegionResponse]
    active_count: int
    declared_count: int
    note: str


class AreaTotalResponse(HeliosModel):
    """One measured resource total for a whole county or state.

    Every field here is ``reported``: an agency measured it and published it.
    Nothing on this model is derived by Helios.
    """

    area_kind: str
    """``county`` or ``state``. Not interchangeable -- see the response note."""

    area_code: str
    """County FIPS, or a two-letter state code."""

    area_name: str
    metric: str
    sector: str
    """``all`` where the publisher gives no sectoral breakdown."""

    value: float
    unit: str
    reference_year: int
    assertion_class: str
    source_slug: str
    source_name: str


class HeliosShareResponse(HeliosModel):
    """Helios's own sites expressed against a reported area total.

    Both sides are stated separately and the ratio between them is a *ratio of
    an inference to a measurement*, which is weaker than either. It carries the
    inferred band, not just a midpoint, for that reason.
    """

    metric: str
    unit: str
    area_kind: str
    area_name: str
    area_value: float
    """The reported total. Whole-area, covering every user in it."""

    area_reference_year: int

    sites_counted: int
    inferred_lower: float
    inferred_likely: float
    inferred_upper: float

    share_lower_pct: float | None
    share_likely_pct: float | None
    share_upper_pct: float | None

    method: str
    assumptions: dict[str, Any]
    caveat: str


class AreaConsumptionResponse(HeliosModel):
    """What a region already consumes, and how Helios's sites compare to it.

    The point of this endpoint is scale. An inferred 40 MW site means nothing
    without knowing what the surrounding area already draws, and the surrounding
    figure is one Helios did not produce.

    The two halves are deliberately not merged. ``totals`` is reported and
    ``comparisons`` is inferred, and a reader must be able to tell at a glance
    which is which.
    """

    region_slug: str
    region_name: str
    totals: list[AreaTotalResponse]
    comparisons: list[HeliosShareResponse]
    granularity_note: str
    """Why the water and electricity figures cover different geographies."""

    note: str


__all__ = [
    "AnalyticsStagesResponse",
    "AreaConsumptionResponse",
    "AreaTotalResponse",
    "AssertedValue",
    "ConnectorRunResponse",
    "DependencyResponse",
    "DocumentResponse",
    "DocumentVersionResponse",
    "EstimateResponse",
    "EvidenceItemResponse",
    "EvidenceListResponse",
    "HealthResponse",
    "HeliosShareResponse",
    "MapFeatureCollection",
    "OrganizationSummary",
    "PageMeta",
    "ParcelSummary",
    "PredictionResponse",
    "ProvenanceCompletenessResponse",
    "ReadinessResponse",
    "RegionListResponse",
    "RegionResponse",
    "ScoreExplanation",
    "ScoreHistoryResponse",
    "SiteDetail",
    "SiteListResponse",
    "SiteSummary",
    "SourceListResponse",
    "SourceReference",
    "SourceResponse",
    "StageDistributionEntry",
    "StageTransition",
    "TimelineEntry",
    "TimelineResponse",
]
