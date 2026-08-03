import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ObservatoryMap } from "./ObservatoryMap";
import type { FacilityCollection } from "@/lib/observatory";

/**
 * MapLibre needs WebGL, which jsdom does not have. The layers are stubbed as
 * markers so the tests can assert *which* layers exist and when, which is the
 * part of this component that carries logic. What the canvas paints is not
 * testable here and is not what these tests claim to cover.
 */
vi.mock("react-map-gl/maplibre", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="map">{children}</div>
  ),
  Layer: ({
    id,
    layout,
    paint,
    filter,
  }: {
    id: string;
    layout?: { visibility?: string };
    paint?: Record<string, unknown>;
    filter?: unknown;
  }) => (
    <div
      data-testid={`layer-${id}`}
      data-visibility={layout?.visibility ?? "visible"}
      data-paint={JSON.stringify(paint ?? {})}
      data-filter={JSON.stringify(filter ?? null)}
    />
  ),
  Source: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  NavigationControl: () => null,
  Popup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/InfrastructureMap", () => ({ basemapStyle: () => ({}) }));
vi.mock("@/components/ThemeToggle", () => ({ useTheme: () => "light" }));

const FACILITIES = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-77.5, 39.0] },
      properties: { id: "way/1", footprint_m2: 12000, name: "A facility" },
    },
  ],
} as unknown as FacilityCollection;

const GRID = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [-77.4, 39.1] },
      properties: { kind: "substation", voltage_kv: 230 },
    },
  ],
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: true, json: async () => GRID }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ObservatoryMap", () => {
  it("does not download the grid until someone asks for it", () => {
    render(<ObservatoryMap facilities={FACILITIES} />);

    // 62,427 points is not something to fetch for a reader who came to look at
    // data centres. If this regresses the cost is silent - the map still works,
    // it just costs everyone megabytes.
    expect(fetch).not.toHaveBeenCalled();
    expect(
      screen.getByTestId("layer-facility-building-point"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("layer-facility-other-point"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("layer-substation-point")).toBeNull();
  });

  it("keeps land and construction geometry out of the building-area scale", () => {
    render(<ObservatoryMap facilities={FACILITIES} />);

    expect(screen.getByTestId("layer-facility-building-point")).toHaveAttribute(
      "data-paint",
      expect.stringContaining("footprint_m2"),
    );
    expect(
      screen.getByTestId("layer-facility-other-point"),
    ).not.toHaveAttribute(
      "data-paint",
      expect.stringContaining("footprint_m2"),
    );
  });

  it("does not treat an unclassified feature as a building", () => {
    render(<ObservatoryMap facilities={FACILITIES} />);

    const filterOf = (id: string) =>
      JSON.parse(screen.getByTestId(id).getAttribute("data-filter") ?? "null");

    // `get` on a missing property yields null. Matching on equality keeps an
    // unclassified feature out of the area-sized layer, and the inequality puts
    // it in the fixed-size one. A `has`-based fallback would do the opposite and
    // silently restore the land-as-floor-plate conflation this split exists to
    // remove.
    expect(filterOf("layer-facility-building-point")).toEqual([
      "==",
      ["get", "site_class"],
      "building",
    ]);
    expect(filterOf("layer-facility-other-point")).toEqual([
      "!=",
      ["get", "site_class"],
      "building",
    ]);
  });

  it("fetches the published grid once a grid layer is switched on", async () => {
    render(<ObservatoryMap facilities={FACILITIES} />);
    fireEvent.click(screen.getByRole("button", { name: /substations/i }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(
      String((fetch as never as ReturnType<typeof vi.fn>).mock.calls[0][0]),
    ).toMatch(/\/data\/grid\.geojson$/);
    expect(
      await screen.findByTestId("layer-substation-point"),
    ).toBeInTheDocument();
  });

  it("downloads the grid only once for both grid layers", async () => {
    render(<ObservatoryMap facilities={FACILITIES} />);
    fireEvent.click(screen.getByRole("button", { name: /substations/i }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: /power plants/i }));
    await waitFor(() =>
      expect(screen.getByTestId("layer-plant-point")).toHaveAttribute(
        "data-visibility",
        "visible",
      ),
    );
    // Substations and plants come from one file; asking again would refetch
    // eleven megabytes to show points already in memory.
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("hides a switched-off layer rather than unmounting the source", async () => {
    render(<ObservatoryMap facilities={FACILITIES} />);
    fireEvent.click(screen.getByRole("button", { name: /substations/i }));
    await screen.findByTestId("layer-substation-point");

    fireEvent.click(screen.getByRole("button", { name: /data centres/i }));
    expect(screen.getByTestId("layer-facility-building-point")).toHaveAttribute(
      "data-visibility",
      "none",
    );
    expect(screen.getByTestId("layer-facility-other-point")).toHaveAttribute(
      "data-visibility",
      "none",
    );
  });

  it("says the grid failed rather than showing a country with no substations", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<ObservatoryMap facilities={FACILITIES} />);
    fireEvent.click(screen.getByRole("button", { name: /substations/i }));

    // An empty map here would read as a finding about the United States.
    expect(
      await screen.findByText(/grid layer could not be loaded/i),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("layer-facility-building-point"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("layer-facility-other-point"),
    ).toBeInTheDocument();
  });
});
