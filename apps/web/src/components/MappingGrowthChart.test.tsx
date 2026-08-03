import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MappingGrowthChart } from "./MappingGrowthChart";
import type { SeriesPoint } from "@/lib/observatory";

function series(periods: string[]): SeriesPoint[] {
  return periods.map((period, i) => ({
    period,
    count: i * 10,
    change: 10,
    footprint_m2: i * 1000,
  }));
}

/**
 * The chart's whole reason for existing is that its early years must not read
 * as history. `telecom=data_center` was barely used before 2017, so the
 * near-zero start describes the tag rather than the country. If a restyle drops
 * the hatched band or its label, the remaining curve silently claims a
 * precision it does not have — which is the single most damaging error
 * available to this project.
 */
describe("MappingGrowthChart", () => {
  it("hatches and labels the stretch that must not be read as history", () => {
    const { container } = render(
      <MappingGrowthChart
        points={series(["2013-01", "2015-01", "2020-01", "2024-01"])}
      />,
    );

    expect(
      container.querySelector('rect[fill="url(#unreliable-hatch)"]'),
    ).not.toBeNull();
    expect(container.querySelector("pattern#unreliable-hatch")).not.toBeNull();
    expect(screen.getByText(/undercounted/i)).toBeInTheDocument();
  });

  it("does not qualify a series that begins after the tag was adopted", () => {
    const { container } = render(
      <MappingGrowthChart points={series(["2019-01", "2021-01", "2024-01"])} />,
    );

    // A band drawn over reliable years would disclaim data that needs no
    // disclaimer, which erodes the warning where it genuinely applies.
    expect(
      container.querySelector('rect[fill="url(#unreliable-hatch)"]'),
    ).toBeNull();
    expect(screen.queryByText(/undercounted/i)).toBeNull();
  });

  it("describes itself to a screen reader as mapping, never as construction", () => {
    render(
      <MappingGrowthChart points={series(["2013-01", "2018-01", "2024-01"])} />,
    );

    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";
    expect(label).toMatch(/recorded in OpenStreetMap/i);
    expect(label).toMatch(/unreliable/i);
    expect(label).not.toMatch(/\bbuilt\b|\bconstructed\b|\bopened\b/i);
  });

  it("states in the caption that no construction dates exist", () => {
    const { container } = render(
      <MappingGrowthChart points={series(["2013-01", "2020-01"])} />,
    );

    const caption = container.querySelector("figcaption")?.textContent ?? "";
    expect(caption).toMatch(/carries no construction dates/i);
  });

  it("refuses to draw a series too short to have a shape", () => {
    render(<MappingGrowthChart points={series(["2020-01"])} />);
    expect(screen.getByText(/not enough history/i)).toBeInTheDocument();
  });
});
