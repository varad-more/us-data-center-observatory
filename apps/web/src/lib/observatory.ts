/**
 * Typed reader for the observatory dataset.
 *
 * These payloads are built by `scripts/observatory/build_site_data.py` from
 * committed CSVs, not by the Helios API, so they live under `public/data`
 * rather than `public/api` and are read through their own client. As with the
 * API client, responses are validated with Zod at the boundary: a schema drift
 * should surface as a build error, not as a page quietly rendering a figure
 * whose meaning has changed.
 *
 * The vocabulary distinction this module exists to protect: a facility's
 * location is *reported* by OpenStreetMap contributors, the date it appears is
 * *observed* (when the map recorded it, never when it was built), and its power
 * and water are *inferred* - a share of a national total, allocated by building
 * floor area.
 *
 * That last word carries weight. The same tags are used for machine halls and
 * for the land parcels campuses sit on, and only the first is a floor plate, so
 * `site_class` says which a row is and only buildings are given a power figure.
 */
import { z } from "zod";

import fs from "fs/promises";
import path from "path";

import { DATA_BASE } from "./regionPath";

// Re-exported so server code keeps importing from this module, while the client
// picker can reach the same helpers without dragging `fs` into the bundle.
export { DATA_BASE, regionIdFromSlug, regionSlug } from "./regionPath";

export const observatoryMetaSchema = z.object({
  generated_at: z.string(),
  facility_count: z.number(),
  // Optional for the same reason as the grid fields: a dataset built before
  // buildings and land parcels were told apart carries neither.
  building_count: z.number().optional(),
  construction_count: z.number().optional(),
  region_count: z.number(),
  series_count: z.number(),
  // Optional so a dataset built before the grid layer existed still validates
  // rather than failing the build on a field it could not have carried.
  substation_count: z.number().optional(),
  plant_count: z.number().optional(),
  national_mw: z.number(),
  national_reference_year: z.number(),
  total_footprint_m2: z.number(),
  note: z.string(),
});

export type ObservatoryMeta = z.infer<typeof observatoryMetaSchema>;

export const regionSchema = z.object({
  region_id: z.string(),
  kind: z.enum(["county", "state"]),
  name: z.string(),
  state: z.string(),
  fips: z.string(),
  facility_count: z.number(),
  // `footprint_m2` is building floor area alone. Land parcels and construction
  // sites are measured too, but kept in their own fields: adding them together
  // produces a number in square metres that describes no physical thing.
  building_count: z.number().optional(),
  site_count: z.number().optional(),
  construction_count: z.number().optional(),
  footprint_m2: z.number(),
  site_area_m2: z.number().optional(),
  construction_area_m2: z.number().optional(),
  est_mw: z.number(),
  est_gal_per_day: z.number(),
  // Grid context, present only for regions the grid stage has placed assets in.
  // Absent rather than zero, so "no substations mapped here" stays
  // distinguishable from "the grid dataset has not been built".
  substation_count: z.number().optional(),
  bulk_substation_count: z.number().optional(),
  max_voltage_kv: z.number().optional(),
  plant_count: z.number().optional(),
  plant_capacity_mw: z.number().optional(),
  plants_without_capacity: z.number().optional(),
});

export type Region = z.infer<typeof regionSchema>;

export const regionListSchema = z.object({ items: z.array(regionSchema) });

export const seriesPointSchema = z.object({
  period: z.string(),
  count: z.number(),
  change: z.number(),
  footprint_m2: z.number(),
});

export type SeriesPoint = z.infer<typeof seriesPointSchema>;

export const regionSeriesSchema = z.object({
  region_id: z.string(),
  points: z.array(seriesPointSchema),
});

export type RegionSeries = z.infer<typeof regionSeriesSchema>;

export const nationalEnergyPointSchema = z.object({
  year: z.number(),
  electricity_twh: z.number().nullable(),
  water_bgal: z.number().nullable(),
  series_kind: z.enum(["historical", "projection"]),
  scenario: z.string(),
  assertion_class: z.enum(["reported", "predicted"]),
  source: z.string(),
});

export type NationalEnergyPoint = z.infer<typeof nationalEnergyPointSchema>;

export const nationalEnergySchema = z.object({
  items: z.array(nationalEnergyPointSchema),
});

export const facilityPropertiesSchema = z.object({
  id: z.string(),
  footprint_m2: z.number(),
  // What that area measures: a building's floor plate, the boundary of a campus
  // ("site"), a site under construction, or a node with no area at all.
  site_class: z.enum(["building", "site", "construction", "point"]).optional(),
  name: z.string().optional(),
  operator: z.string().optional(),
  ref: z.string().optional(),
  county_fips: z.string().optional(),
  state: z.string().optional(),
  first_seen: z.string().optional(),
  est_mw: z.number().optional(),
});

export const facilityCollectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(
    z.object({
      type: z.literal("Feature"),
      geometry: z.object({
        type: z.literal("Point"),
        coordinates: z.tuple([z.number(), z.number()]),
      }),
      properties: facilityPropertiesSchema,
    }),
  ),
});

export type FacilityCollection = z.infer<typeof facilityCollectionSchema>;

export const changeSchema = z.object({
  id: z.string(),
  date: z.string(),
  kind: z.enum(["creation", "deletion"]),
  state: z.string(),
  county_fips: z.string(),
  name: z.string().default(""),
  county_name: z.string().default(""),
});

export type Change = z.infer<typeof changeSchema>;

export const changeListSchema = z.object({ items: z.array(changeSchema) });

export class ObservatoryDataError extends Error {
  constructor(
    message: string,
    readonly dataPath: string,
  ) {
    super(message);
    this.name = "ObservatoryDataError";
  }
}

async function read<T>(
  fileName: string,
  schema: { parse: (value: unknown) => T },
): Promise<T> {
  if (typeof window !== "undefined") {
    const res = await fetch(`${DATA_BASE}/${fileName}`);
    if (!res.ok) {
      throw new ObservatoryDataError(`Could not load ${fileName}`, fileName);
    }
    return schema.parse(await res.json());
  }
  const filePath = path.join(process.cwd(), "public", "data", fileName);
  const raw = await fs.readFile(filePath, "utf-8");
  return schema.parse(JSON.parse(raw));
}

/**
 * Read a payload that may legitimately not exist yet.
 *
 * The growth series depends on a slow backfill against a volunteer-run API. A
 * page that needs it should say plainly that it is not there rather than fail
 * the build, so that the rest of the dataset stays publishable meanwhile.
 */
async function readOptional<T>(
  fileName: string,
  schema: { parse: (value: unknown) => T },
): Promise<T | null> {
  try {
    return await read(fileName, schema);
  } catch {
    return null;
  }
}

export function getObservatoryMeta(): Promise<ObservatoryMeta> {
  return read("meta.json", observatoryMetaSchema);
}

export async function getRegions(): Promise<Region[]> {
  const payload = await read("regions.json", regionListSchema);
  return payload.items;
}

export function getFacilities(): Promise<FacilityCollection> {
  return read("facilities.geojson", facilityCollectionSchema);
}

export async function getNationalEnergy(): Promise<NationalEnergyPoint[]> {
  const payload = await read("national_energy.json", nationalEnergySchema);
  return payload.items;
}

export async function getChanges(): Promise<Change[]> {
  const payload = await readOptional("changes.json", changeListSchema);
  return payload?.items ?? [];
}

/** Read one region's monthly series, or null when the backfill has not run. */
export function getRegionSeries(regionId: string): Promise<RegionSeries | null> {
  return readOptional(
    `series/${regionId.replace(":", "-")}.json`,
    regionSeriesSchema,
  );
}

/** Convenience wrapper for the national series, which the growth page leads on. */
export function getNationalSeries(): Promise<RegionSeries | null> {
  return getRegionSeries("national:US");
}

/**
 * Facilities belonging to one region.
 *
 * Counties match on FIPS and states on the two-letter code, so a county's
 * facilities are necessarily a subset of its state's. That overlap is the
 * reason nothing on the site ever adds a county total to a state total.
 */
export async function getRegionFacilities(
  regionId: string,
): Promise<FacilityCollection["features"]> {
  const [kind, value] = regionId.split(":");
  const collection = await getFacilities();
  if (kind === "county") {
    return collection.features.filter((f) => f.properties.county_fips === value);
  }
  if (kind === "state") {
    return collection.features.filter((f) => f.properties.state === value);
  }
  return collection.features;
}
