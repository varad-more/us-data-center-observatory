import { describe, expect, it } from "vitest";

import {
  facilityClassLabel,
  formatMappedArea,
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

  it("links only recognised OpenStreetMap element ids", () => {
    expect(openStreetMapElementUrl("way/154213519")).toBe(
      "https://www.openstreetmap.org/way/154213519",
    );
    expect(openStreetMapElementUrl("not-an-element")).toBeNull();
  });
});
