import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceEntry } from "./SourceEntry";
import type { Source } from "@/lib/types";

const SOURCE = {
  id: "source-1",
  slug: "adwr-water-records",
  name: "Arizona Department of Water Resources Data",
  agency: "Arizona Department of Water Resources",
  jurisdiction: "Arizona",
  category: "water",
  base_url: "https://example.com",
  access_method: "bulk_download",
  update_frequency: null,
  license_name: null,
  license_url: null,
  attribution_required: false,
  attribution_text: null,
  robots_policy_status: null,
  geographic_coverage: "Arizona",
  historical_coverage: "Long historical series.",
  contains_personal_data: false,
  reliability_score: null,
  known_schema_issues: null,
  notes: "Needed before any water-use scenario is published. Deferred.",
  connector_status: "planned",
  connector_slug: null,
  access_limitation: null,
  last_success_at: null,
  document_count: 0,
} satisfies Source;

describe("SourceEntry", () => {
  it("renders a registry note even when there is no access limitation", () => {
    render(<SourceEntry source={SOURCE} />);

    expect(
      screen.getByRole("link", { name: "Arizona Department of Water Resources Data" }),
    ).toHaveAttribute("href", "https://example.com");
    expect(screen.getByText("Registry note.")).toBeInTheDocument();
    expect(screen.getByText(/Needed before any water-use scenario/)).toBeInTheDocument();
  });

  it("keeps a note and an access limitation as separate statements", () => {
    render(
      <SourceEntry
        source={{
          ...SOURCE,
          notes: "Why this source matters.",
          access_limitation: "Why Helios cannot read it.",
        }}
      />,
    );

    expect(screen.getByText(/Why this source matters/)).toBeInTheDocument();
    expect(screen.getByText(/Why Helios cannot read it/)).toBeInTheDocument();
    expect(screen.getByText("Access limitation.")).toBeInTheDocument();
  });
});
