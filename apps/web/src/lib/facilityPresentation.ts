/**
 * Presentation helpers for OpenStreetMap facility geometry.
 *
 * `footprint_m2` is the historical field name in the published GeoJSON. Its
 * physical meaning depends on `site_class`: a building floor plate, a campus
 * land boundary, or an area mapped as under construction. This module keeps
 * that distinction at every UI surface that has to name the value.
 */

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

export function openStreetMapElementUrl(id: string): string | null {
  const match = /^(node|way|relation)\/(\d+)$/.exec(id);
  if (!match) return null;
  return `https://www.openstreetmap.org/${match[1]}/${match[2]}`;
}
