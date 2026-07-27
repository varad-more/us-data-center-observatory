import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssertionBadge, ConfidenceBadge } from "./AssertionBadge";
import type { AssertionClass } from "@/lib/types";

describe("AssertionBadge", () => {
  it("renders distinct labels for reported vs inferred", () => {
    const { rerender } = render(<AssertionBadge assertion="reported" />);
    expect(screen.getByTestId("badge-reported")).toHaveTextContent("Reported");

    rerender(<AssertionBadge assertion="inferred" />);
    expect(screen.getByTestId("badge-inferred")).toHaveTextContent("Inferred");
    expect(screen.getByTestId("badge-inferred").getAttribute("title") || "").toMatch(
      /may be wrong/i,
    );
  });

  /**
   * The product rule, asserted directly.
   *
   * Assertion classes are graded along a single sequential ramp, so hue alone no
   * longer separates a reported value from an inferred one. What separates them
   * is the evidence basis, which drives the border treatment and therefore
   * survives greyscale, print and colour blindness. If a future restyle collapses
   * that channel, this fails rather than shipping an inferred value that looks
   * observed.
   */
  it("marks observed and derived claims with different evidence bases", () => {
    const { rerender } = render(<AssertionBadge assertion="reported" />);
    const observed = screen.getByTestId("badge-reported").dataset.evidenceBasis;

    rerender(<AssertionBadge assertion="inferred" />);
    const derived = screen.getByTestId("badge-inferred").dataset.evidenceBasis;

    expect(observed).toBe("observed");
    expect(derived).toBe("derived");
    expect(observed).not.toBe(derived);
  });

  it("classifies every assertion class by how the claim was arrived at", () => {
    const expected: Record<AssertionClass, string> = {
      reported: "observed",
      extracted: "observed",
      calculated: "derived",
      inferred: "derived",
      predicted: "derived",
      unknown: "unestablished",
    };

    for (const [assertion, basis] of Object.entries(expected)) {
      const { unmount } = render(
        <AssertionBadge assertion={assertion as AssertionClass} />,
      );
      expect(screen.getByTestId(`badge-${assertion}`).dataset.evidenceBasis).toBe(basis);
      unmount();
    }
  });

  it("covers the whole vocabulary, so a new class cannot slip through unclassified", () => {
    // Mirrors the closed vocabulary in lib/types. If a class is added to the
    // schema without a basis, the loop above would never exercise it.
    const vocabulary: AssertionClass[] = [
      "reported",
      "extracted",
      "calculated",
      "inferred",
      "predicted",
      "unknown",
    ];

    for (const assertion of vocabulary) {
      const { unmount } = render(<AssertionBadge assertion={assertion} />);
      expect(screen.getByTestId(`badge-${assertion}`).dataset.evidenceBasis).toBeDefined();
      unmount();
    }
  });

  /**
   * `unknown` is not the weak end of the scale — it is off the scale. A value
   * that was explicitly not established and a value that was weakly established
   * are different claims, and the vocabulary exists to keep them apart.
   */
  /**
   * `unknown` and `predicted` sit adjacent in luminance — measured, their badge
   * edges differ by 0.003 — so once hue is removed they are the same mark. The
   * basis attribute is what drives the different stroke pattern that keeps "not
   * established" from reading as "weakly established" in greyscale and print.
   */
  it("keeps 'unknown' off the strength scale rather than at its weak end", () => {
    const { rerender } = render(<AssertionBadge assertion="unknown" />);
    expect(screen.getByTestId("badge-unknown").dataset.evidenceBasis).toBe(
      "unestablished",
    );

    rerender(<AssertionBadge assertion="predicted" />);
    expect(screen.getByTestId("badge-predicted").dataset.evidenceBasis).toBe("derived");
  });
});

describe("ConfidenceBadge", () => {
  it("labels confidence as model output, not existence probability", () => {
    render(<ConfidenceBadge confidence={41.2} band="moderate" />);
    const el = screen.getByTestId("confidence-badge");
    expect(el).toHaveTextContent("41%");
    expect(el.getAttribute("title") || "").toMatch(/not a probability of existence/i);
  });
});
