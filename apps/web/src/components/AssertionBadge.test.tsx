import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssertionBadge, ConfidenceBadge } from "./AssertionBadge";

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
});

describe("ConfidenceBadge", () => {
  it("labels confidence as model output, not existence probability", () => {
    render(<ConfidenceBadge confidence={41.2} band="moderate" />);
    const el = screen.getByTestId("confidence-badge");
    expect(el).toHaveTextContent("41%");
    expect(el.getAttribute("title") || "").toMatch(/not a probability of existence/i);
  });
});
