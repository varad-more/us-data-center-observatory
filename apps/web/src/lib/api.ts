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

import fs from "fs/promises";
import path from "path";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "/project-helios";
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || `${BASE_PATH}/api`;

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
  apiPath: string,
  schema: { parse: (value: unknown) => T },
  init?: RequestInit,
): Promise<T> {
  // Strip query parameters for static mock reading
  const cleanPath = apiPath.split("?")[0];
  const jsonPath = cleanPath.endsWith(".json") ? cleanPath : `${cleanPath}.json`;

  if (typeof window !== "undefined") {
    const url = `${API_BASE}${jsonPath.startsWith("/") ? "" : "/"}${jsonPath}`;
    try {
      const res = await fetch(url, init);
      if (!res.ok) {
        throw new ApiError(`Mock API fetch failed for ${cleanPath}: ${res.statusText}`, res.status, cleanPath);
      }
      const data = await res.json();
      return schema.parse(data);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      console.error(`Failed to fetch static mock for ${cleanPath}:`, error);
      throw new ApiError(`Mock API request failed for ${cleanPath}`, 404, cleanPath);
    }
  } else {
    let filePath = path.join(process.cwd(), "public", "api", cleanPath);
    if (!filePath.endsWith(".json")) {
      filePath += ".json";
    }

    try {
      const data = await fs.readFile(filePath, "utf-8");
      return schema.parse(JSON.parse(data));
    } catch (error) {
      console.error(`Failed to read static mock for ${cleanPath}:`, error);
      throw new ApiError(`Mock API file not found for ${cleanPath}`, 404, cleanPath);
    }
  }
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

// Download targets. A static export cannot build a zip on demand, so the
// evidence bundle is published as the same provenance payload the API would
// have placed inside it. Keyed on project_code, matching the exported layout.
export function evidenceJsonUrl(siteId: string): string {
  return `${API_BASE}/sites/${siteId}/evidence.json`;
}

export function sitesCsvUrl(): string {
  return `${API_BASE}/sites.csv`;
}

export function sitesGeoJsonUrl(): string {
  return `${API_BASE}/sites.geojson`;
}

