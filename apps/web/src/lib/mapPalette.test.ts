import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  MAP_FACILITY,
  MAP_PAPER,
  MAP_PLANT,
  MAP_SUBSTATION,
  MAP_UNPLACED,
  STAGE_RAMP,
  stageColourExpression,
} from "./mapPalette";

/**
 * The map palette has to be literals — MapLibre paint expressions take resolved
 * colours, and `light-dark()` in a custom property does not resolve through
 * `getComputedStyle`. So the stylesheet is read here instead and every value is
 * checked against the token it mirrors.
 *
 * This exists because the duplication failed silently once: three map components
 * each carried the old ivory palette, the site moved to chart paper, and nothing
 * anywhere said the maps had been left behind.
 */
const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");

function token(name: string): { light: string; dark: string } {
  const match = css.match(
    new RegExp(`--${name}:\\s*light-dark\\((#[0-9a-f]{6}),\\s*(#[0-9a-f]{6})\\)`, "i"),
  );
  if (!match) throw new Error(`--${name} is not a light-dark() pair in globals.css`);
  return { light: match[1], dark: match[2] };
}

function relativeLuminance(hex: string): number {
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

describe("map palette", () => {
  it.each([
    ["page", MAP_PAPER],
    ["pen-1", MAP_FACILITY],
    ["pen-2", MAP_SUBSTATION],
    ["pen-3", MAP_PLANT],
    ["unmeasured-edge", MAP_UNPLACED],
  ])("matches --%s in both themes", (name, pair) => {
    expect(pair).toEqual(token(name));
  });

  it("spans the sequential ramp's own range", () => {
    // Nine stages against seven tokens, so the ends are what can be asserted
    // exactly — and the ends are what fixes the ramp to the stylesheet's scale.
    expect(relativeLuminance(STAGE_RAMP.light[0])).toBeCloseTo(
      relativeLuminance(token("seq-1").light),
      2,
    );
    expect(relativeLuminance(STAGE_RAMP.light[8])).toBeCloseTo(
      relativeLuminance(token("seq-7").light),
      2,
    );
  });

  it("is monotonic, so a later stage never reads as a weaker one", () => {
    const light = STAGE_RAMP.light.map(relativeLuminance);
    expect(light).toEqual([...light].sort((a, b) => b - a));
  });

  it("runs dark as the reverse of light", () => {
    expect(STAGE_RAMP.dark).toEqual([...STAGE_RAMP.light].reverse());
  });

  it("clears the 3:1 mark floor against the paper it is drawn on", () => {
    const contrast = (a: string, b: string) => {
      const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
      return (hi + 0.05) / (lo + 0.05);
    };
    for (const theme of ["light", "dark"] as const) {
      for (const pair of [MAP_FACILITY, MAP_SUBSTATION, MAP_PLANT]) {
        expect(contrast(pair[theme], MAP_PAPER[theme])).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it("falls back to the unplaced colour rather than to a step of the scale", () => {
    const expression = stageColourExpression("light");
    expect(expression[expression.length - 1]).toBe(MAP_UNPLACED.light);
  });
});
