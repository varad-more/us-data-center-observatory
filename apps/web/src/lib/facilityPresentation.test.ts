import { describe, expect, it } from "vitest";

import {
  facilityClassLabel,
  formatMappedArea,
  formatRegionFootprintKm2,
  formatRegionMw,
  openStreetMapElementUrl,
} from "./facilityPresentation";

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
