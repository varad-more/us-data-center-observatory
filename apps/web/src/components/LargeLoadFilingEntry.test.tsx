import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LargeLoadFilingEntry } from "./LargeLoadFilingEntry";
import type { LargeLoadFiling } from "@/lib/types";

const FILING = {
  evidence_id: "evidence-1",
  docket_number: "U-21990",
  decision_date: "2025-12-18",
  decision_status: "conditionally_approved",
  utility_name: "DTE Electric Co.",
  customer_name: "Green Chile Ventures LLC",
  parent_company_name: "Oracle Corp.",
  project_type: "data_center",
  reported_load_mw: 1383,
  load_assertion_class: "reported",
  location_name: "Saline Township",
  county_name: "Washtenaw",
  state_code: "MI",
  location_precision: "township",
  geometry: null,
  summary: "MPSC conditionally approved the service contract.",
  snippet: "The customer requested 1,383 megawatts in Saline Township.",
  snippet_locator: "MPSC press release, December 18, 2025",
  evidence_assertion_class: "extracted",
  source: {
    document_id: "document-1",
    document_version_id: "version-1",
    source_slug: "mpsc-large-load-contracts",
    source_name: "Michigan Public Service Commission large-load decisions",
    agency: "Michigan Public Service Commission",
    source_url: "https://www.michigan.gov/mpsc/example",
    retrieved_at: "2026-07-29T12:00:00Z",
    content_sha256:
      "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    parser_version: "1.0.0",
    attribution_text: null,
  },
} satisfies LargeLoadFiling;

describe("LargeLoadFilingEntry", () => {
  it("keeps reported contracted load distinct from site capacity", () => {
    render(<LargeLoadFilingEntry filing={FILING} />);

    expect(screen.getByText("1,383 MW")).toBeInTheDocument();
    expect(screen.getByTestId("badge-reported")).toHaveTextContent("Reported");
    expect(screen.getByText(/not measured consumption/)).toBeInTheDocument();
    expect(screen.queryByText(/operator/i)).not.toBeInTheDocument();
  });

  it("publishes township precision and checkable provenance", () => {
    render(<LargeLoadFilingEntry filing={FILING} />);

    expect(screen.getByText("Saline Township")).toBeInTheDocument();
    expect(screen.getByText(/no site point published/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Check the official MPSC disclosure" }),
    ).toHaveAttribute("href", FILING.source.source_url);
    expect(screen.getByText(/SHA-256 1234567890ab/)).toBeInTheDocument();
  });
});
