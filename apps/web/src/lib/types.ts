/**
 * Runtime-validated API contracts.
 *
 * Every response is parsed through Zod rather than cast. A backend change that
 * drops a provenance field should fail loudly at the boundary, not render as a
 * blank badge that quietly understates how much Helios knows.
 */
import { z } from "zod";

export const assertionClassSchema = z.enum([
  "reported",
  "extracted",
  "calculated",
  "inferred",
  "predicted",
  "unknown",
]);

export type AssertionClass = z.infer<typeof assertionClassSchema>;

export const confidenceBandSchema = z.enum([
  "very_low",
  "low",
  "moderate",
  "high",
  "very_high",
]);

export type ConfidenceBand = z.infer<typeof confidenceBandSchema>;

export const pageMetaSchema = z.object({
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  has_more: z.boolean(),
});

export const siteSummarySchema = z.object({
  id: z.string(),
  project_code: z.string(),
  display_name: z.string().nullable(),
  site_kind: z.string(),
  site_kind_assertion: assertionClassSchema,
  jurisdiction: z.string().nullable(),
  county: z.string(),
  region_slug: z.string(),
  current_stage: z.number(),
  current_stage_label: z.string(),
  current_confidence: z.number(),
  stage_confidence: z.number(),
  confidence_band: confidenceBandSchema,
  first_signal_date: z.string().nullable(),
  latest_signal_date: z.string().nullable(),
  evidence_count: z.number(),
  total_acres: z.number().nullable(),
  parcel_count: z.number(),
  operator_status: z.string(),
  stage_last_changed_at: z.string().nullable(),
  score_last_calculated_at: z.string().nullable(),
  centroid: z.array(z.number()).nullable(),
  is_synthetic: z.boolean(),
});

export type SiteSummary = z.infer<typeof siteSummarySchema>;

export const siteListSchema = z.object({
  items: z.array(siteSummarySchema),
  meta: pageMetaSchema,
});

export const sourceReferenceSchema = z.object({
  document_id: z.string(),
  document_version_id: z.string(),
  source_slug: z.string(),
  source_name: z.string(),
  agency: z.string(),
  source_url: z.string(),
  retrieved_at: z.string(),
  content_sha256: z.string(),
  parser_version: z.string().nullable(),
  attribution_text: z.string().nullable(),
});

export const evidenceItemSchema = z.object({
  id: z.string(),
  evidence_kind: z.string(),
  summary: z.string(),
  snippet: z.string().nullable(),
  snippet_locator: z.string().nullable(),
  observed_at: z.string(),
  assertion_class: assertionClassSchema,
  extraction_method: z.string(),
  polarity: z.string(),
  confidence: z.number(),
  human_review_status: z.string(),
  is_standing_condition: z.boolean(),
  normalized_values: z.record(z.unknown()),
  source: sourceReferenceSchema,
});

export type EvidenceItem = z.infer<typeof evidenceItemSchema>;

export const stageTransitionSchema = z.object({
  id: z.string(),
  from_stage: z.number().nullable(),
  from_stage_label: z.string().nullable(),
  to_stage: z.number(),
  to_stage_label: z.string(),
  effective_date: z.string(),
  detected_at: z.string(),
  is_downgrade: z.boolean(),
  confidence: z.number(),
  rationale: z.string(),
  triggering_evidence_ids: z.array(z.string()),
  detection_lag_days: z.number().nullable(),
});

export type StageTransition = z.infer<typeof stageTransitionSchema>;

export const timelineEntrySchema = z.object({
  entry_type: z.string(),
  occurred_on: z.string(),
  title: z.string(),
  detail: z.string(),
  evidence: evidenceItemSchema.nullable(),
  stage_transition: stageTransitionSchema.nullable(),
  confidence_delta: z.number().nullable(),
});

export type TimelineEntry = z.infer<typeof timelineEntrySchema>;

export const timelineSchema = z.object({
  site_id: z.string(),
  project_code: z.string(),
  entries: z.array(timelineEntrySchema),
  first_signal_date: z.string().nullable(),
  latest_signal_date: z.string().nullable(),
});

export const scoreExplanationSchema = z.object({
  rule_id: z.string(),
  evidence_kind: z.string().nullable(),
  label: z.string(),
  detail: z.string().nullable(),
  base_weight: z.number(),
  applied_weight: z.number(),
  confidence_multiplier: z.number(),
  recency_multiplier: z.number(),
  polarity: z.string(),
  evidence_record_id: z.string().nullable(),
});

export type ScoreExplanation = z.infer<typeof scoreExplanationSchema>;

export const predictionSchema = z.object({
  id: z.string(),
  calculated_at: z.string(),
  as_of_date: z.string(),
  predicted_stage: z.number().nullable(),
  predicted_stage_label: z.string().nullable(),
  raw_score: z.number(),
  confidence: z.number(),
  confidence_band: confidenceBandSchema,
  positive_contribution: z.number(),
  negative_contribution: z.number(),
  evidence_considered: z.number(),
  distinct_evidence_kinds: z.number(),
  is_backtest: z.boolean(),
  summary: z.string().nullable(),
  model_name: z.string(),
  model_version: z.string(),
  explanations: z.array(scoreExplanationSchema),
});

export type Prediction = z.infer<typeof predictionSchema>;

export const parcelSchema = z.object({
  id: z.string(),
  apn: z.string(),
  apn_formatted: z.string().nullable(),
  situs_address: z.string().nullable(),
  situs_city: z.string().nullable(),
  owner_name: z.string().nullable(),
  owner_is_redacted: z.boolean(),
  land_use_description: z.string().nullable(),
  lot_size_acres: z.number().nullable(),
  last_deed_date: z.string().nullable(),
  last_deed_number: z.string().nullable(),
  last_deed_url: z.string().nullable(),
  last_sale_price: z.number().nullable(),
  assessor_url: z.string().nullable(),
  link_reason: z.string().nullable(),
  link_confidence: z.number().nullable(),
});

export type Parcel = z.infer<typeof parcelSchema>;

export const organizationSchema = z.object({
  id: z.string(),
  canonical_name: z.string(),
  role: z.string(),
  organization_type: z.string().nullable(),
  is_suspected_shell: z.boolean(),
  shell_indicators: z.array(z.string()),
  mailing_city: z.string().nullable(),
  mailing_state: z.string().nullable(),
  attribution_note: z.string(),
});

export type Organization = z.infer<typeof organizationSchema>;

export const dependencySchema = z.object({
  id: z.string(),
  infrastructure_kind: z.string(),
  label: z.string(),
  dependency_status: z.string(),
  is_blocking: z.boolean(),
  match_method: z.string().nullable(),
  distance_meters: z.number().nullable(),
  confidence: z.number(),
  assertion_class: assertionClassSchema,
  notes: z.string().nullable(),
  voltage_kv: z.number().nullable(),
  operator_name: z.string().nullable(),
});

export type Dependency = z.infer<typeof dependencySchema>;

export const estimateSchema = z.object({
  id: z.string(),
  estimate_type: z.string(),
  unit: z.string(),
  lower_value: z.number().nullable(),
  likely_value: z.number().nullable(),
  upper_value: z.number().nullable(),
  method: z.string(),
  assertion_class: assertionClassSchema,
  confidence: z.number(),
  assumptions: z.record(z.unknown()),
  calculated_at: z.string(),
  notes: z.string().nullable(),
});

export type Estimate = z.infer<typeof estimateSchema>;

export const stageGrowthPointSchema = z.object({
  month: z.string(),
  // JSON object keys are always strings, so the stage index arrives as one.
  cumulative_by_stage: z.record(z.number()),
  sites_tracked: z.number(),
});

export type StageGrowthPoint = z.infer<typeof stageGrowthPointSchema>;

export const stageGrowthSchema = z.object({
  region_slug: z.string().nullable(),
  points: z.array(stageGrowthPointSchema),
  note: z.string(),
});

export type StageGrowth = z.infer<typeof stageGrowthSchema>;

export const detectionLagEntrySchema = z.object({
  project_code: z.string(),
  to_stage: z.number(),
  stage_label: z.string(),
  effective_date: z.string(),
  detected_at: z.string(),
  lag_days: z.number(),
});

export const detectionLagSchema = z.object({
  region_slug: z.string().nullable(),
  transitions: z.number(),
  median_lag_days: z.number().nullable(),
  p90_lag_days: z.number().nullable(),
  min_lag_days: z.number().nullable(),
  max_lag_days: z.number().nullable(),
  slowest: z.array(detectionLagEntrySchema),
  note: z.string(),
});

export type DetectionLag = z.infer<typeof detectionLagSchema>;

export const siteDetailSchema = siteSummarySchema.extend({
  summary: z.string().nullable(),
  boundary: z.record(z.unknown()).nullable(),
  parcels: z.array(parcelSchema),
  organizations: z.array(organizationSchema),
  dependencies: z.array(dependencySchema),
  estimates: z.array(estimateSchema),
  latest_prediction: predictionSchema.nullable(),
  stage_history: z.array(stageTransitionSchema),
  attributions: z.array(z.string()),
});

export type SiteDetail = z.infer<typeof siteDetailSchema>;

export const featureCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(z.record(z.unknown())),
  attributions: z.array(z.string()),
});

export type FeatureCollection = z.infer<typeof featureCollectionSchema>;

export const sourceSchema = z.object({
  id: z.string(),
  slug: z.string(),
  name: z.string(),
  agency: z.string(),
  jurisdiction: z.string(),
  category: z.string(),
  base_url: z.string(),
  access_method: z.string(),
  update_frequency: z.string().nullable(),
  license_name: z.string().nullable(),
  license_url: z.string().nullable(),
  attribution_required: z.boolean(),
  attribution_text: z.string().nullable(),
  robots_policy_status: z.string().nullable(),
  geographic_coverage: z.string().nullable(),
  historical_coverage: z.string().nullable(),
  contains_personal_data: z.boolean(),
  reliability_score: z.number().nullable(),
  known_schema_issues: z.string().nullable(),
  notes: z.string().nullable(),
  connector_status: z.string().nullable(),
  connector_slug: z.string().nullable(),
  access_limitation: z.string().nullable(),
  last_success_at: z.string().nullable(),
  document_count: z.number(),
});

export type Source = z.infer<typeof sourceSchema>;

export const sourceListSchema = z.object({
  items: z.array(sourceSchema),
  coverage_summary: z.record(z.number()),
});

export const largeLoadFilingSchema = z.object({
  evidence_id: z.string(),
  docket_number: z.string(),
  decision_date: z.string(),
  decision_status: z.string(),
  utility_name: z.string(),
  customer_name: z.string(),
  parent_company_name: z.string().nullable(),
  project_type: z.string(),
  reported_load_mw: z.number(),
  load_assertion_class: assertionClassSchema,
  location_name: z.string(),
  county_name: z.string(),
  state_code: z.string(),
  location_precision: z.string(),
  geometry: z.null(),
  summary: z.string(),
  snippet: z.string(),
  snippet_locator: z.string().nullable(),
  evidence_assertion_class: assertionClassSchema,
  source: sourceReferenceSchema,
});

export type LargeLoadFiling = z.infer<typeof largeLoadFilingSchema>;

export const largeLoadFilingListSchema = z.object({
  items: z.array(largeLoadFilingSchema),
  note: z.string(),
});

export const regionSchema = z.object({
  slug: z.string(),
  name: z.string(),
  state_code: z.string(),
  coverage: z.enum(["active", "declared"]),
  counties: z.array(z.string()),
  cities: z.array(z.string()),
  bbox: z.array(z.number()),
  note: z.string(),
  site_count: z.number(),
});

export type Region = z.infer<typeof regionSchema>;

export const regionListSchema = z.object({
  items: z.array(regionSchema),
  active_count: z.number(),
  declared_count: z.number(),
  note: z.string(),
});

export const stageDistributionSchema = z.object({
  region_slug: z.string().nullable(),
  total_sites: z.number(),
  stages: z.array(
    z.object({
      stage: z.number(),
      stage_label: z.string(),
      site_count: z.number(),
      mean_confidence: z.number().nullable(),
    }),
  ),
});

export const provenanceSchema = z.object({
  total_evidence_records: z.number(),
  with_document_version: z.number(),
  with_snippet: z.number(),
  with_locator: z.number(),
  with_observation_date: z.number(),
  completeness_ratio: z.number(),
  note: z.string(),
});

export const areaTotalSchema = z.object({
  area_kind: z.enum(["county", "state"]),
  area_code: z.string(),
  area_name: z.string(),
  metric: z.string(),
  sector: z.string(),
  value: z.number(),
  unit: z.string(),
  reference_year: z.number(),
  assertion_class: assertionClassSchema,
  source_slug: z.string(),
  source_name: z.string(),
});

export type AreaTotal = z.infer<typeof areaTotalSchema>;

export const heliosShareSchema = z.object({
  metric: z.string(),
  unit: z.string(),
  area_kind: z.enum(["county", "state"]),
  area_name: z.string(),
  area_value: z.number(),
  area_reference_year: z.number(),
  sites_counted: z.number(),
  inferred_lower: z.number(),
  inferred_likely: z.number(),
  inferred_upper: z.number(),
  share_lower_pct: z.number().nullable(),
  share_likely_pct: z.number().nullable(),
  share_upper_pct: z.number().nullable(),
  method: z.string(),
  assumptions: z.record(z.unknown()),
  caveat: z.string(),
});

export type HeliosShare = z.infer<typeof heliosShareSchema>;

export const areaConsumptionSchema = z.object({
  region_slug: z.string(),
  region_name: z.string(),
  totals: z.array(areaTotalSchema),
  comparisons: z.array(heliosShareSchema),
  granularity_note: z.string(),
  note: z.string(),
});

export type AreaConsumption = z.infer<typeof areaConsumptionSchema>;

export const stateCoverageSchema = z.object({
  state_code: z.string(),
  facility_count: z.number(),
  site_count: z.number(),
  region_slug: z.string().nullable(),
  region_coverage: z.enum(["active", "declared"]).nullable(),
});

export type StateCoverage = z.infer<typeof stateCoverageSchema>;

export const nationalCoverageSchema = z.object({
  items: z.array(stateCoverageSchema),
  states_with_facilities: z.number(),
  states_with_sites: z.number(),
  facility_total: z.number(),
  site_total: z.number(),
  note: z.string(),
});

export type NationalCoverage = z.infer<typeof nationalCoverageSchema>;
