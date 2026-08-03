import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecorderChart, type Channel } from "./RecorderChart";
import { monthIndex } from "@/lib/recorder";

/**
 * The front page's chart carries three of this project's load-bearing claims,
 * and each of them is the kind that fails silently in a restyle: the hatched
 * stretch that stops early years reading as history, the blank paper that must
 * never resolve to a zero, and a resting readout that shows a month the
 * instrument actually recorded.
 *
 * The equivalent guards already exist for the chart this one replaced on the
 * home page. Moving the surface without moving the guards would have left the
 * most consequential page on the site as the only one nothing checks.
 */
function channel(over: Partial<Channel> = {}): Channel {
  return {
    id: "count",
    name: "Facilities on the map",
    unit: "elements",
    pen: 1,
    claim: "observed",
    height: 100,
    max: 100,
    render: "step",
    points: [
      { t: monthIndex("2018-01"), v: 10 },
      { t: monthIndex("2024-01"), v: 90 },
    ],
    absentLabel: "no paper",
    ...over,
  };
}

function renderChart(props: Partial<Parameters<typeof RecorderChart>[0]> = {}) {
  return render(
    <RecorderChart
      channels={[channel()]}
      deadBandUntil="2017-01"
      lastAdvance="2024-01"
      fromPeriod="2014-01"
      toPeriod="2026-12"
      restAt="2024-01"
      {...props}
    >
      <div />
    </RecorderChart>,
  );
}

describe("RecorderChart", () => {
  it("hatches and labels the stretch that must not be read as history", () => {
    const { container } = renderChart();

    expect(
      container.querySelector('rect[fill="url(#pp-deadband)"]'),
    ).not.toBeNull();
    expect(container.querySelector("pattern#pp-deadband")).not.toBeNull();
    expect(screen.getByText(/undercounted/i)).toBeInTheDocument();
  });

  it("does not qualify paper that begins after the tag was adopted", () => {
    // A band drawn over reliable years disclaims data that needs no disclaimer,
    // which erodes the warning where it genuinely applies.
    const { container } = renderChart({
      fromPeriod: "2019-01",
      deadBandUntil: "2017-01",
    });

    expect(
      container.querySelector('rect[fill="url(#pp-deadband)"]'),
    ).toBeNull();
    expect(screen.queryByText(/undercounted/i)).toBeNull();
  });

  it("reads absent where the instrument has no reading, never zero", () => {
    // The whole reason this page is a chart recorder. A month outside the
    // channel's span is not a month in which nothing was built; it is a month
    // that was not measured, and a 0 there would be a fabricated observation.
    renderChart({ restAt: "2026-11" });

    expect(screen.getByText("no paper")).toBeInTheDocument();
    expect(screen.queryByText(/^0 elements$/)).toBeNull();
  });

  it("rests on a month that was actually recorded", () => {
    // Resting at the right-hand edge of the paper put the instrument's default
    // state at three lines of "no paper", which is true and useless.
    renderChart({ restAt: "2024-01" });

    expect(screen.getByText("Jan 2024")).toBeInTheDocument();
    expect(screen.getByText("90 elements")).toBeInTheDocument();
  });

  it("marks where the paper runs out rather than trailing the trace onward", () => {
    renderChart({ lastAdvance: "2024-01" });
    expect(screen.getByText(/chart ends/i)).toBeInTheDocument();
  });

  it("holds a published-years channel to its published years", () => {
    // The electricity pen lifts between LBNL's published years. Reporting a
    // value for an unpublished year would put a figure in the reader's hands
    // that nobody published.
    renderChart({
      channels: [
        channel({
          id: "power",
          name: "US data-centre electricity",
          unit: "TWh",
          render: "spot",
          absentLabel: "not published",
          points: [
            { t: monthIndex("2023-07"), v: 176 },
            { t: monthIndex("2024-07"), v: 192 },
          ],
        }),
      ],
      restAt: "2020-01",
    });

    expect(screen.getByText("not published")).toBeInTheDocument();
  });
});
