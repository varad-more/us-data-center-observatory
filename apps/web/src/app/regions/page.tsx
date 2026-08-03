/**
 * How many data centres sit in a given area, and what share of national load
 * their footprint accounts for.
 *
 * This is the page that answers the plainest question the observatory gets
 * asked. It leads with the counties, because that is the resolution at which
 * data-centre siting is actually fought over, and because a state figure hides
 * that a single county can hold more than the rest of its state combined.
 */
import type { Metadata } from "next";

import { RegionTable } from "@/components/RegionTable";
import { getObservatoryMeta, getRegions } from "@/lib/observatory";

export const metadata: Metadata = {
  title: "Regions",
  description:
    "Mapped data centres by US county and state, with each region's share of national data-centre electricity and water.",
};

export default async function RegionsPage() {
  const [regions, meta] = await Promise.all([
    getRegions(),
    getObservatoryMeta(),
  ]);

  const counties = regions.filter((r) => r.kind === "county");
  const states = regions.filter((r) => r.kind === "state");
  const topCounty = [...counties].sort(
    (a, b) => b.facility_count - a.facility_count,
  )[0];

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>Regions</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {meta.facility_count.toLocaleString()} data centres that
            OpenStreetMap records in the United States, placed in{" "}
            {counties.length} counties across {states.length} states.
          </p>
        </div>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Mapped facilities</div>
          <div className="metric-value num">
            {meta.facility_count.toLocaleString()}
          </div>
          <div className="metric-sub">reported by OSM contributors</div>
        </div>
        <div className="metric">
          <div className="metric-label">Counties</div>
          <div className="metric-value num">{counties.length}</div>
          <div className="metric-sub">holding at least one</div>
        </div>
        <div className="metric">
          <div className="metric-label">Total floor area</div>
          <div className="metric-value num">
            {(meta.total_footprint_m2 / 1e6).toFixed(0)}
          </div>
          <div className="metric-sub">
            km² across {(meta.building_count ?? 0).toLocaleString()} buildings
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Densest county</div>
          <div className="metric-value num">
            {topCounty?.facility_count ?? 0}
          </div>
          <div className="metric-sub">
            {topCounty ? `${topCounty.name}, ${topCounty.state}` : "—"}
          </div>
        </div>
      </div>

      <div className="notice" style={{ marginTop: "1rem" }}>
        <strong>A count here is a count of what has been mapped.</strong> A
        county showing zero has not been surveyed and found empty. Either nobody
        has mapped it or it genuinely holds none, and this page cannot tell you
        which. OpenStreetMap coverage follows contributor activity, and
        contributor activity is uneven.
      </div>

      <RegionTable regions={regions} />
    </div>
  );
}
