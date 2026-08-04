/**
 * Presentation helpers for OpenStreetMap facility geometry.
 *
 * `footprint_m2` is the historical field name in the published GeoJSON. Its
 * physical meaning depends on `site_class`: a building floor plate, a campus
 * land boundary, or an area mapped as under construction. This module keeps
 * that distinction at every UI surface that has to name the value.
 */

import type { Region } from "./observatory";

export type FacilitySiteClass = "building" | "site" | "construction" | "point";

export function facilityClassLabel(siteClass?: FacilitySiteClass): string {
  switch (siteClass) {
    case "building":
      return "Building";
    case "site":
      return "Campus boundary";
    case "construction":
      return "Under construction";
    case "point":
    default:
      return "Point";
  }
}

function formatAreaValue(areaM2: number): string {
  if (areaM2 >= 1e6) return `${(areaM2 / 1e6).toFixed(2)} km²`;
  return `${Math.round(areaM2).toLocaleString()} m²`;
}

export function formatMappedArea(
  value: unknown,
  siteClass?: FacilitySiteClass,
): string {
  const areaM2 = typeof value === "number" ? value : 0;
  if (areaM2 <= 0) return "area not mapped";

  const area = formatAreaValue(areaM2);
  switch (siteClass) {
    case "building":
      return `${area} building floor plate`;
    case "site":
      return `${area} campus boundary`;
    case "construction":
      return `${area} area mapped under construction`;
    default:
      return `${area} mapped area`;
  }
}

/**
 * A region's floor area and its allocated load, without ever printing a zero
 * that is really an absence.
 *
 * Both columns were rendering `0.00` and `0` in three different situations that
 * mean three different things, and 127 of 323 regions were in one of them:
 *
 * - 53 regions hold only points and campus boundaries. No building means no
 *   floor plate was measured, so there is nothing to take a share of the
 *   national total — the honest cell is an em dash, and `0` was the site's own
 *   cardinal rule broken in its widest table.
 * - 74 regions have a real footprint under 5,000 m² that `toFixed(2)` rounds
 *   away, and 15 have a real allocation under half a megawatt that `Math.round`
 *   rounds away. Those are measurements, and printing them as zero says the
 *   opposite of what was measured.
 * - The rest are ordinary values.
 *
 * `<0.01` and `<1` keep a small measured thing distinguishable from an
 * unmeasured one, which is the entire distinction this project exists to hold.
 */
export interface RegionFigures {
  footprint_m2: number;
  est_mw: number;
  building_count?: number;
}

/** Everything a region's metric cards read. A `Region` satisfies it as it is. */
export type RegionTotals = RegionFigures &
  Pick<
    Region,
    "site_count" | "construction_count" | "site_area_m2" | "est_gal_per_day"
  >;

/**
 * The national figures, summed from the state rows.
 *
 * `regions.json` holds counties and states and no national row, so every
 * `region?.…` on the region page fell through to its else branch: the United
 * States page reported "km² across 0 buildings" and left three of its four
 * metrics as bare dashes, while `meta.json` carried the floor area, the
 * building count and the megawatts all along.
 *
 * Summed here rather than published into `regions.json`, because a row there
 * would appear in the regions table and in the picker, and whether the United
 * States belongs in a list of counties is a question about what those surfaces
 * are for, not about this defect.
 *
 * States, not counties: a county with no state would be dropped from a state
 * sum and double-counted in a county-and-state one, and every facility that
 * carries a county carries the state it is in.
 */
export function nationalTotals(regions: Region[]): RegionTotals {
  return regions
    .filter((r) => r.kind === "state")
    .reduce<RegionTotals>(
      (sum, r) => ({
        building_count: (sum.building_count ?? 0) + (r.building_count ?? 0),
        site_count: (sum.site_count ?? 0) + (r.site_count ?? 0),
        construction_count:
          (sum.construction_count ?? 0) + (r.construction_count ?? 0),
        footprint_m2: sum.footprint_m2 + r.footprint_m2,
        site_area_m2: (sum.site_area_m2 ?? 0) + (r.site_area_m2 ?? 0),
        est_mw: sum.est_mw + r.est_mw,
        est_gal_per_day: sum.est_gal_per_day + r.est_gal_per_day,
      }),
      {
        building_count: 0,
        site_count: 0,
        construction_count: 0,
        footprint_m2: 0,
        site_area_m2: 0,
        est_mw: 0,
        est_gal_per_day: 0,
      },
    );
}

export function formatRegionFootprintKm2(region: RegionFigures): string {
  if (region.building_count === 0 || region.footprint_m2 <= 0) return "—";
  const km2 = region.footprint_m2 / 1e6;
  return km2 < 0.005 ? "<0.01" : km2.toFixed(2);
}

export function formatRegionMw(region: RegionFigures): string {
  if (region.building_count === 0 || region.est_mw <= 0) return "—";
  return region.est_mw < 0.5
    ? "<1"
    : Math.round(region.est_mw).toLocaleString();
}

export function openStreetMapElementUrl(id: string): string | null {
  const match = /^(node|way|relation)\/(\d+)$/.exec(id);
  if (!match) return null;
  return `https://www.openstreetmap.org/${match[1]}/${match[2]}`;
}
