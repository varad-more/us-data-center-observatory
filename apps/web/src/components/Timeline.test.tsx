/**
 * The one thing this component must never do is offer provenance it cannot
 * honour. Evidence replayed from a recorded fixture carries no reachable URL,
 * and a "View original evidence" link pointing at a reserved `.invalid` host
 * looks exactly like checkable provenance while being impossible to check.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Timeline } from "./Timeline";
import type { TimelineEntry } from "@/lib/types";

function entryWithSourceUrl(source_url: string): TimelineEntry {
  return {
    entry_type: "evidence",
    occurred_on: "2025-04-02",
    title: "Parcel classified for data-centre use",
    detail: "Assessor land-use code updated.",
    confidence_delta: null,
    stage_transition: null,
    evidence: {
      id: "evidence-1",
      evidence_kind: "parcel_use_code",
      summary: "Land use recorded as DATA CENTERS.",
      snippet: null,
      snippet_locator: null,
      observed_at: "2025-04-02",
      assertion_class: "reported",
      extraction_method: "structured_field",
      polarity: "positive",
      confidence: 0.9,
      human_review_status: "not_required",
      is_standing_condition: true,
      normalized_values: {},
      source: {
        document_id: "doc-1",
        document_version_id: "docv-1",
        source_slug: "maricopa-assessor-parcels",
        source_name: "Maricopa County Assessor Parcel Layer",
        agency: "Maricopa County Assessor",
        source_url,
        retrieved_at: "2025-04-02T00:00:00Z",
        content_sha256: "a".repeat(64),
        parser_version: "1",
        attribution_text: null,
      },
    },
  };
}

describe("Timeline evidence provenance", () => {
  it("links evidence that has a reachable source document", () => {
    render(<Timeline entries={[entryWithSourceUrl("https://mcassessor.maricopa.gov/parcel/1")]} />);

    expect(screen.getByRole("link", { name: "View original evidence" })).toHaveAttribute(
      "href",
      "https://mcassessor.maricopa.gov/parcel/1",
    );
  });

  it("offers no link for a replayed fixture, and says why", () => {
    render(<Timeline entries={[entryWithSourceUrl("https://example.invalid/recorded")]} />);

    expect(screen.queryByRole("link", { name: "View original evidence" })).toBeNull();
    expect(screen.getByText(/Recorded fixture/)).toBeInTheDocument();
  });

  it("still pins the bytes with a hash when the document is unreachable", () => {
    render(<Timeline entries={[entryWithSourceUrl("https://example.invalid/recorded")]} />);

    expect(screen.getByText(/^sha256:/)).toBeInTheDocument();
  });
});
