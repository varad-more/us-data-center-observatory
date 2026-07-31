import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ChangesPage from "./page";
import type { Change, ObservatoryMeta } from "@/lib/observatory";

/**
 * The wording on this page is the product, not decoration. ohsome reports a
 * deletion whenever an element stops matching the data-centre filter, so a
 * mapper retagging `building=data_center` to `building=yes` is indistinguishable
 * from a building coming down. A restyle that shortened "removed from OSM" to
 * "closed" would turn a fact about the map into a claim about the world, and
 * nothing would fail. These tests are what fails.
 */
const CHANGES: Change[] = [
  {
    id: "way/1",
    date: "2026-06-19",
    kind: "creation",
    state: "VA",
    county_fips: "51107",
    name: "A facility",
    county_name: "Loudoun County",
  },
  {
    id: "way/2",
    date: "2026-06-18",
    kind: "deletion",
    state: "AZ",
    county_fips: "04013",
    name: "",
    county_name: "Maricopa County",
  },
];

const META = {
  last_polled: "2026-07-29",
  facility_count: 1853,
  region_count: 323,
  series_count: 330,
  national_mw: 21918,
  national_reference_year: 2024,
  total_footprint_m2: 19998284,
  note: "",
} as ObservatoryMeta;

vi.mock("@/lib/observatory", () => ({
  getChanges: async () => CHANGES,
  getObservatoryMeta: async () => META,
}));

/** The page is an async server component; await it, then render what it returns. */
async function renderPage() {
  render(await ChangesPage());
}

describe("ChangesPage", () => {
  it("labels a disappearance as a removal from the map, never as a demolition", async () => {
    await renderPage();

    expect(screen.getByText("removed from OSM")).toBeInTheDocument();
    // "demolished" is deliberately not banned outright - the page uses it to
    // deny it. What must never appear is a word that asserts the building is
    // gone rather than off the map.
    expect(screen.queryByText(/\bclosed\b/i)).toBeNull();
    expect(screen.queryByText(/\bshut down\b/i)).toBeNull();
    expect(screen.queryByText(/\bdecommissioned\b/i)).toBeNull();
  });

  it("says outright that a removal is not a demolition", async () => {
    await renderPage();

    // The disclaimer is the other half: without it a reader is left to infer
    // that a row labelled "removed" means the building is gone.
    expect(screen.getByText(/a removal is not a demolition/i)).toBeInTheDocument();
    expect(screen.getByText(/not necessarily demolished/i)).toBeInTheDocument();
  });

  it("does not invent a name for a facility that has left the map", async () => {
    await renderPage();

    // Names are read from the current snapshot, so a removed facility has none.
    // A placeholder would imply the name was never recorded rather than that it
    // is no longer readable.
    expect(screen.getByText("no longer on the map")).toBeInTheDocument();
  });

  it("dates an edit rather than a construction", async () => {
    await renderPage();

    expect(
      screen.getByText(/dates are when the edit was made, not when anything was built/i),
    ).toBeInTheDocument();
  });
});
