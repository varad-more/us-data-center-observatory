import { describe, expect, it } from "vitest";

import {
  facilityClassLabel,
  formatMappedArea,
  formatRegionFootprintKm2,
  formatRegionMw,
  nationalTotals,
  openStreetMapElementUrl,
} from "./facilityPresentation";
import type { Region } from "./observatory";

describe("facility geometry presentation", () => {
  it("names the physical quantity instead of calling every area a footprint", () => {
    expect(formatMappedArea(12_000, "building")).toBe(
      "12,000 m² building floor plate",
    );
    expect(formatMappedArea(2_500_000, "site")).toBe(
      "2.50 km² campus boundary",
    );
    expect(formatMappedArea(850_000, "construction")).toBe(
      "850,000 m² area mapped under construction",
    );
  });

  it("does not turn an unknown area into zero", () => {
    expect(formatMappedArea(0, "point")).toBe("area not mapped");
    expect(formatMappedArea(undefined, "building")).toBe("area not mapped");
  });

  it("keeps construction distinct from an operating building", () => {
    expect(facilityClassLabel("building")).toBe("Building");
    expect(facilityClassLabel("construction")).toBe("Under construction");
  });

  /**
   * The regions table printed `0.00` km² and `0` MW for 127 of 323 rows, and
   * the three situations behind that zero mean different things. These are the
   * cases, and the point of each is that its output is distinguishable.
   */
  it("never prints a region's unmeasured floor area as zero", () => {
    // 53 regions: points and campus boundaries only, nothing to measure.
    const noBuilding = { footprint_m2: 0, est_mw: 0, building_count: 0 };
    expect(formatRegionFootprintKm2(noBuilding)).toBe("—");
    expect(formatRegionMw(noBuilding)).toBe("—");
  });

  it("never rounds a real measurement down to zero", () => {
    // Venango County: 32 buildings totalling 2,132 m². Real, and tiny.
    const tiny = { footprint_m2: 2132, est_mw: 2.34, building_count: 32 };
    expect(formatRegionFootprintKm2(tiny)).toBe("<0.01");
    expect(formatRegionMw({ ...tiny, est_mw: 0.47 })).toBe("<1");
  });

  it("still reads an ordinary region as a plain number", () => {
    const loudoun = {
      footprint_m2: 2_770_000,
      est_mw: 3034,
      building_count: 239,
    };
    expect(formatRegionFootprintKm2(loudoun)).toBe("2.77");
    expect(formatRegionMw(loudoun)).toBe("3,034");
  });

  it("keeps a small measurement distinguishable from an absent one", () => {
    // The whole point: these two must not render the same string.
    expect(
      formatRegionFootprintKm2({
        footprint_m2: 900,
        est_mw: 1,
        building_count: 1,
      }),
    ).not.toBe(
      formatRegionFootprintKm2({
        footprint_m2: 0,
        est_mw: 0,
        building_count: 0,
      }),
    );
  });

  it("links only recognised OpenStreetMap element ids", () => {
    expect(openStreetMapElementUrl("way/154213519")).toBe(
      "https://www.openstreetmap.org/way/154213519",
    );
    expect(openStreetMapElementUrl("not-an-element")).toBeNull();
  });
});

/**
 * `regions.json` carries no national row, so the United States page used to
 * fall through every optional-chained region field and publish "km² across 0
 * buildings" — a measured 19,998,284 m² across 1,506 buildings rendered as a
 * zero, which is the one thing this project exists not to do.
 */
describe("national totals", () => {
  const region = (over: Partial<Region>): Region => ({
    region_id: "state:VA",
    kind: "state",
    name: "Virginia",
    state: "VA",
    fips: "51",
    facility_count: 0,
    footprint_m2: 0,
    est_mw: 0,
    est_gal_per_day: 0,
    ...over,
  });

  it("adds the states up", () => {
    const totals = nationalTotals([
      region({ building_count: 300, footprint_m2: 1_000, est_mw: 40 }),
      region({
        region_id: "state:AZ",
        state: "AZ",
        building_count: 200,
        footprint_m2: 500,
        est_mw: 60,
        est_gal_per_day: 12,
      }),
    ]);
    expect(totals.building_count).toBe(500);
    expect(totals.footprint_m2).toBe(1_500);
    expect(totals.est_mw).toBe(100);
    expect(totals.est_gal_per_day).toBe(12);
  });

  it("counts each facility once, not once per region it belongs to", () => {
    // Counties are inside states, so summing both would double the country.
    const totals = nationalTotals([
      region({ building_count: 300, est_mw: 40 }),
      region({
        region_id: "county:51107",
        kind: "county",
        name: "Loudoun County",
        fips: "51107",
        building_count: 250,
        est_mw: 33,
      }),
    ]);
    expect(totals.building_count).toBe(300);
    expect(totals.est_mw).toBe(40);
  });

  it("treats an absent optional field as absent rather than failing on it", () => {
    const totals = nationalTotals([region({ footprint_m2: 10, est_mw: 2 })]);
    expect(totals.building_count).toBe(0);
    expect(totals.site_area_m2).toBe(0);
  });
});
