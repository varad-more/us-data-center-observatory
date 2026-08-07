import type { Metadata } from "next";

import { LargeLoadFilingEntry } from "@/components/LargeLoadFilingEntry";
import { listLargeLoadFilings } from "@/lib/api";
import { routeMeta } from "@/lib/site";

export const metadata: Metadata = {
  title: "Large-load filings",
  description:
    "Site-specific utility-regulator filings carrying reported large-load values, with source documents and honest location precision.",
  ...routeMeta("/large-load-filings/"),
};

export default async function LargeLoadFilingsPage() {
  const payload = await listLargeLoadFilings();
  const totalReportedMw = payload.items.reduce(
    (sum, filing) => sum + filing.reported_load_mw,
    0,
  );
  const states = new Set(payload.items.map((filing) => filing.state_code));

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>Reported large-load filings</h1>
          <p className="tagline">
            Site-specific public decisions that name a large electricity
            request. Each record keeps the regulator&apos;s words, the reported
            load class, and the location precision together.
          </p>
        </div>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Published filings</div>
          <div className="metric-value num">
            {payload.items.length.toLocaleString()}
          </div>
          <div className="metric-sub">site-specific regulator records</div>
        </div>
        <div className="metric">
          <div className="metric-label">Reported contracted load</div>
          <div className="metric-value num">
            {totalReportedMw.toLocaleString("en-US")} MW
          </div>
          <div className="metric-sub">sum of the records below</div>
        </div>
        <div className="metric">
          <div className="metric-label">States represented</div>
          <div className="metric-value num">{states.size.toLocaleString()}</div>
          <div className="metric-sub">coverage is not comprehensive</div>
        </div>
        <div className="metric">
          <div className="metric-label">Exact site points</div>
          <div className="metric-value">None</div>
          <div className="metric-sub">unknown is not mapped as zero</div>
        </div>
      </div>

      <div className="notice">
        <strong>
          This is a filing register, not a national project census.
        </strong>{" "}
        Helios publishes only reviewed, site-specific state-regulator
        disclosures that its connector can reproduce. A state or project missing
        from this page falls outside the sources Helios reads. That is all it
        means.
      </div>

      <div className="notice">
        <strong>Reported contracted load is not operating load.</strong> Nor is
        it generating capacity, a promise of grid availability, or proof that
        anything has been built. A filing that names a township is mapped to
        that township. Helios does not manufacture a point from a place name.
      </div>

      {payload.items.length > 0 ? (
        payload.items.map((filing) => (
          <LargeLoadFilingEntry key={filing.evidence_id} filing={filing} />
        ))
      ) : (
        <div className="card">
          <h2 className="card-title">No filings in this snapshot</h2>
          <p className="muted" style={{ marginBottom: 0 }}>
            The empty result is published as unknown coverage, never as zero
            large-load activity.
          </p>
        </div>
      )}

      <p className="small muted">{payload.note}</p>
    </div>
  );
}
