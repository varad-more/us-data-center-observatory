import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * `--header-h` is a hand-written sum of heights declared a few hundred lines
 * below it, and the recorder's margin plates stick to that number. It was wrong
 * once already — a 106px constant against a header that ranged 106–190px, which
 * slid the plates up underneath it — and nothing in a jsdom test lays the page
 * out, so the failure was invisible to the suite and only showed in a browser.
 *
 * This reads the stylesheet as text and re-adds the parts. It cannot prove the
 * rendered height, but it does fail the moment someone changes a row height and
 * leaves the sum behind, which is how the number went wrong the first time.
 */
const css = readFileSync(join(__dirname, "globals.css"), "utf8");

function declaredPx(pattern: RegExp): number {
  const match = css.match(pattern);
  if (!match) throw new Error(`no declaration matched ${pattern}`);
  return Number.parseInt(match[1], 10);
}

const RULE_PX = 1; // .site-header { border-bottom: 1px solid var(--rule) }

describe("--header-h", () => {
  it("equals the two rows plus the bottom rule when the rail is expanded", () => {
    const brandRow = declaredPx(/\.brand \{[^}]*height: (\d+)px/);
    const navRow = declaredPx(/^\.nav \{[^}]*height: (\d+)px/m);
    const declared = declaredPx(/^:root \{\s*--header-h: (\d+)px/m);

    expect(declared).toBe(brandRow + navRow + RULE_PX);
  });

  it("equals the single row plus the bottom rule when the rail is collapsed", () => {
    const collapsedRow = declaredPx(
      /@media \(max-width: 1024px\) \{\s*\.brand,\s*\.header-tools \{\s*height: (\d+)px/,
    );
    const declared = declaredPx(
      /@media \(max-width: 1024px\) \{\s*:root \{\s*--header-h: (\d+)px/,
    );

    expect(declared).toBe(collapsedRow + RULE_PX);
  });

  it("is the only place the header's height is written down", () => {
    // The recorder's sticky plates must read the variable, never a copy of it.
    const recorder = readFileSync(join(__dirname, "recorder.css"), "utf8");
    expect(recorder).not.toMatch(/--pp-header-h/);
    expect(recorder).toMatch(/top: var\(--header-h\)/);
  });
});
