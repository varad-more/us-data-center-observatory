/**
 * The chart primitives carry the parts of the front page that would fail
 * silently: a projection that is subtly not equal-area still draws a
 * plausible-looking map, and a step path that interpolates still draws a
 * plausible-looking curve. These check the properties that make them right,
 * not the strings they happen to produce.
 */
import { describe, expect, it } from "vitest";

import {
  albersUsa,
  binToGrid,
  dropFlatRuns,
  fitExtent,
  formatCompact,
  formatPeriod,
  niceTicks,
  ringsToPath,
  scaleLinear,
  stepPath,
} from "./recorder";

describe("scaleLinear", () => {
  it("maps the domain onto the range", () => {
    const s = scaleLinear([0, 100], [0, 500]);
    expect(s(0)).toBe(0);
    expect(s(50)).toBe(250);
    expect(s(100)).toBe(500);
  });

  it("pins a zero-width domain to the middle instead of returning NaN", () => {
    // A county with one facility that never moved has a flat series, and a
    // NaN here would render the whole row as an empty trace rather than a
    // flat one - which is exactly the distinction this page exists to keep.
    const s = scaleLinear([5, 5], [0, 100]);
    expect(s(5)).toBe(50);
    expect(Number.isNaN(s(5))).toBe(false);
  });
});

describe("niceTicks", () => {
  it("uses round intervals a reader can count", () => {
    expect(niceTicks(0, 1800, 3)).toEqual([0, 500, 1000, 1500]);
    expect(niceTicks(0, 150, 3)).toEqual([0, 50, 100, 150]);
  });

  it("does not emit float noise", () => {
    for (const tick of niceTicks(0, 1, 5)) {
      expect(String(tick)).not.toMatch(/\d{6,}/);
    }
  });
});

describe("stepPath", () => {
  it("holds each value until the next reading", () => {
    // Stepped, not interpolated: a diagonal between two months would draw
    // facilities arriving on dates no edit supports.
    const d = stepPath(
      [
        { t: 0, v: 0 },
        { t: 10, v: 100 },
      ],
      (p) => p.t,
      (p) => p.v,
    );
    expect(d).toBe("M 0 0 L 10 0 L 10 100");
  });

  it("returns an empty path for an empty series", () => {
    expect(stepPath([], () => 0, () => 0)).toBe("");
  });
});

describe("dropFlatRuns", () => {
  it("draws the identical stepped path with the interior removed", () => {
    // The property that matters is not "it is shorter" but "it is the same
    // picture". An optimisation that quietly moved a step would be invisible
    // in review and wrong on every county page.
    const full = [
      { t: 0, v: 5 },
      { t: 1, v: 5 },
      { t: 2, v: 5 },
      { t: 3, v: 9 },
      { t: 4, v: 9 },
      { t: 5, v: 2 },
    ];
    const thin = dropFlatRuns(full, (p) => p.v);
    expect(thin.length).toBeLessThan(full.length);

    // The step function a reader traces with their eye - and the one the
    // crosshair reads out - is "the last reading at or before this month".
    // That is the invariant; the path string is allowed to get shorter.
    const sample = (pts: typeof full, t: number) =>
      pts.filter((p) => p.t <= t).at(-1)?.v;
    for (const point of full) {
      expect(sample(thin, point.t)).toBe(sample(full, point.t));
    }
    expect(thin.at(-1)).toEqual(full.at(-1));
  });

  it("keeps both ends and short series untouched", () => {
    expect(dropFlatRuns([{ v: 1 }, { v: 1 }], (p) => p.v)).toHaveLength(2);
    const run = [{ v: 3 }, { v: 3 }, { v: 3 }, { v: 3 }];
    expect(dropFlatRuns(run, (p) => p.v)).toHaveLength(2);
  });
});

describe("albersUsa", () => {
  it("puts north up and east right", () => {
    const [, northY] = albersUsa(-96, 45);
    const [, southY] = albersUsa(-96, 30);
    expect(northY).toBeLessThan(southY);

    const [eastX] = albersUsa(-75, 39);
    const [westX] = albersUsa(-120, 39);
    expect(eastX).toBeGreaterThan(westX);
  });

  it("preserves area, which plotting raw degrees does not", () => {
    // One degree of longitude is a much shorter distance in the north than at
    // the equator. An equal-area projection has to shrink the northern cell in
    // x; plotting degrees straight onto the axes does not, which is the bug
    // this guards.
    const width = (lat: number) =>
      albersUsa(-95, lat)[0] - albersUsa(-97, lat)[0];
    expect(width(47)).toBeLessThan(width(30));
  });
});

describe("fitExtent", () => {
  it("fits points inside the box", () => {
    const pts: [number, number][] = [
      [0, 0],
      [2, 1],
    ];
    const e = fitExtent(pts, 100, 100, 10);
    for (const [x, y] of pts) {
      const px = x * e.scale + e.dx;
      const py = y * e.scale + e.dy;
      expect(px).toBeGreaterThanOrEqual(9.9);
      expect(px).toBeLessThanOrEqual(90.1);
      expect(py).toBeGreaterThanOrEqual(9.9);
      expect(py).toBeLessThanOrEqual(90.1);
    }
  });

  it("uses one scale for both axes so the map is not stretched", () => {
    const e = fitExtent(
      [
        [0, 0],
        [10, 1],
      ],
      100,
      100,
    );
    // A single scalar is the guarantee: there is no separate y scale to drift.
    expect(typeof e.scale).toBe("number");
    expect(e.scale).toBeCloseTo(10, 5);
  });
});

describe("binToGrid", () => {
  it("collapses points that land in the same cell", () => {
    const out = binToGrid(
      [
        [0, 0],
        [1, 1],
        [50, 50],
      ],
      10,
    );
    expect(out).toHaveLength(2);
  });

  // The count is the whole reason this returns cells rather than a set. Without
  // it the plot sheet's underlay is a uniform lattice and the country does not
  // appear, which is exactly how it shipped once.
  it("counts how many points landed in each cell", () => {
    const out = binToGrid(
      [
        [0, 0],
        [1, 1],
        [2, 2],
        [50, 50],
      ],
      10,
    );
    expect(out.map((c) => c[2]).sort()).toEqual([1, 3]);
  });

  it("keeps the total, so no asset is dropped by binning", () => {
    const points: [number, number][] = Array.from({ length: 40 }, (_, i) => [
      i * 3,
      i * 7,
    ]);
    const out = binToGrid(points, 10);
    expect(out.reduce((sum, c) => sum + c[2], 0)).toBe(points.length);
  });
});

describe("ringsToPath", () => {
  /**
   * Relative deltas are the point of this encoding, and the trap that comes
   * with them is drift: round each delta on its own and the error compounds,
   * so a closed ring's last vertex misses its first. On the coastline that is
   * 867 vertices of compounding, and it shows as a notch in the Pacific.
   */
  it("closes a ring where it started, after hundreds of rounded steps", () => {
    // Closed, the way a GeoJSON ring arrives: the last vertex repeats the first.
    const ring: [number, number][] = Array.from({ length: 801 }, (_, i) => {
      const angle = ((i % 800) / 800) * 2 * Math.PI;
      return [500 + 300 * Math.cos(angle), 300 + 220 * Math.sin(angle)];
    });
    const d = ringsToPath([ring]);

    let [x, y] = [0, 0];
    let start: [number, number] | null = null;
    for (const token of d.match(/[Ml][^Mlz]*/gi) ?? []) {
      const [dx, dy] = token.slice(1).trim().split(/\s+/).map(Number);
      if (token[0] === "M") {
        [x, y] = [dx, dy];
        start = [dx, dy];
      } else {
        x += dx;
        y += dy;
      }
    }
    expect(start).not.toBeNull();
    // Within the quantum the encoding rounds to. A drifting implementation
    // lands tens of units away here, not tenths.
    expect(Math.abs(x - start![0])).toBeLessThanOrEqual(0.1);
    expect(Math.abs(y - start![1])).toBeLessThanOrEqual(0.1);
  });

  it("draws every ring, so no island is silently dropped", () => {
    const d = ringsToPath([
      [
        [0, 0],
        [10, 0],
        [10, 10],
        [0, 0],
      ],
      [
        [40, 40],
        [50, 40],
        [50, 50],
        [40, 40],
      ],
    ]);
    expect(d.match(/M/g)).toHaveLength(2);
    expect(d.match(/Z/g)).toHaveLength(2);
  });

  it("skips a vertex that rounds onto the one before it", () => {
    const d = ringsToPath([
      [
        [0, 0],
        [0.01, 0.01],
        [10, 10],
        [0, 0],
      ],
    ]);
    expect(d.match(/l/g)).toHaveLength(2);
  });
});

describe("formatting", () => {
  it("reads periods as a human would say them", () => {
    expect(formatPeriod("2026-06")).toBe("Jun 2026");
    expect(formatPeriod("2014-01")).toBe("Jan 2014");
  });

  it("keeps small figures exact and only abbreviates large ones", () => {
    expect(formatCompact(1853)).toBe("1,853");
    expect(formatCompact(48132)).toBe("48k");
  });
});
