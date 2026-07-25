/**
 * Typed client for the Helios API.
 *
 * Server components call these directly. Responses are validated with Zod at
 * the boundary so a schema drift surfaces as an error rather than as silently
 * missing provenance in the UI.
 */
import {
  featureCollectionSchema,
  provenanceSchema,
  siteDetailSchema,
  siteListSchema,
  sourceListSchema,
  stageDistributionSchema,
  timelineSchema,
  type FeatureCollection,
  type SiteDetail,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_HELIOS_API_URL ??
  process.env.HELIOS_API_URL ??
  "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly path: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  schema: { parse: (value: unknown) => T },
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    // Helios data changes on a connector schedule, not per request. A short
    // revalidation window keeps the observatory responsive without serving
    // stale evidence counts.
    next: { revalidate: 60 },
  });

  if (!response.ok) {
    throw new ApiError(
      `Helios API returned ${response.status} for ${path}`,
      response.status,
      path,
    );
  }

  return schema.parse(await response.json());
}

export interface SiteQuery {
  limit?: number;
  offset?: number;
  region?: string;
  jurisdiction?: string;
  minStage?: number;
  minConfidence?: number;
  sort?: string;
}

function toQueryString(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export function listSites(query: SiteQuery = {}) {
  const qs = toQueryString({
    limit: query.limit ?? 50,
    offset: query.offset,
    region: query.region,
    jurisdiction: query.jurisdiction,
    min_stage: query.minStage,
    min_confidence: query.minConfidence,
    sort: query.sort,
  });
  return request(`/sites${qs}`, siteListSchema);
}

export function getSite(siteId: string): Promise<SiteDetail> {
  return request(`/sites/${siteId}`, siteDetailSchema);
}

export function getTimeline(siteId: string) {
  return request(`/sites/${siteId}/timeline`, timelineSchema);
}

export function getMapSites(bbox?: string): Promise<FeatureCollection> {
  return request(`/map/sites${toQueryString({ bbox })}`, featureCollectionSchema);
}

export function getMapInfrastructure(
  bbox?: string,
  minVoltageKv?: number,
): Promise<FeatureCollection> {
  return request(
    `/map/infrastructure${toQueryString({ bbox, min_voltage_kv: minVoltageKv })}`,
    featureCollectionSchema,
  );
}

export function getMapParcels(
  bbox?: string,
  landUse?: string,
): Promise<FeatureCollection> {
  return request(
    `/map/parcels${toQueryString({ bbox, land_use: landUse })}`,
    featureCollectionSchema,
  );
}

export function listSources() {
  return request("/sources", sourceListSchema);
}

export function getStageDistribution() {
  return request("/analytics/stages", stageDistributionSchema);
}

export function getProvenanceCompleteness() {
  return request("/analytics/provenance", provenanceSchema);
}

export function evidenceBundleUrl(siteId: string): string {
  return `${API_BASE}/exports/site/${siteId}/bundle.zip`;
}

export function evidenceJsonUrl(siteId: string): string {
  return `${API_BASE}/exports/site/${siteId}/evidence.json`;
}

export function sitesCsvUrl(): string {
  return `${API_BASE}/exports/sites.csv`;
}

export function sitesGeoJsonUrl(): string {
  return `${API_BASE}/exports/sites.geojson`;
}

export { API_BASE };
