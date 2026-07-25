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
