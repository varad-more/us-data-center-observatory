/**
 * What Helios holds in each state, and what it does not.
 *
 * This panel exists to be read as a coverage gap, not as a national census.
 * Two counts sit side by side and mean entirely different things: a *facility*
 * is a record EPA publishes, and a *site* is a hypothesis Helios assembled from
 * county parcels and can defend line by line. They are not two measurements of
 * the same quantity, so they are never summed, never charted against one
 * another, and never share a column.
 *
 * The most important row is Virginia: the largest concentration of data-centre
 * capacity in the world, more reported facilities than anywhere else, and zero
 * Helios sites. A reader who leaves with only that has understood the panel.
 */
import type { NationalCoverage, StateCoverage } from "@/lib/types";

function coverageLabel(row: StateCoverage): string {
  if (row.region_coverage === "active") return "Read";
  if (row.region_coverage === "declared") return "Declared, unread";
  return "Not in scope yet";
}

function coveragePill(row: StateCoverage): string {
  // Only a region Helios actually reads earns the positive tone. "Declared"
  // is an intention, and an intention rendered as coverage is the exact
  // confusion the region registry was built to prevent.
  if (row.region_coverage === "active") return "pill pill-positive";
  if (row.region_coverage === "declared") return "pill pill-caution";
  return "pill";
}

export function NationalCoveragePanel({ data }: { data: NationalCoverage }) {
  const rows = [...data.items].sort(
    (a, b) =>
      b.facility_count - a.facility_count ||
      a.state_code.localeCompare(b.state_code),
  );
  const unread = rows.filter(
    (row) => row.facility_count > 0 && row.site_count === 0,
  );

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">National coverage</h2>
        <span className="card-note">
          {data.states_with_facilities} states with reported facilities
        </span>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Reported facilities</div>
          <div className="metric-value num">
            {data.facility_total.toLocaleString()}
          </div>
          <div className="metric-sub">
            EPA records, {data.states_with_facilities} states
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Helios sites</div>
          <div className="metric-value num">
            {data.site_total.toLocaleString()}
          </div>
          <div className="metric-sub">
            built from parcels, {data.states_with_sites}{" "}
            {data.states_with_sites === 1 ? "state" : "states"}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">States unread</div>
          <div className="metric-value num">{unread.length}</div>
          <div className="metric-sub">facilities reported, no sites built</div>
        </div>
        <div className="metric">
          <div className="metric-label">Counties read</div>
          <div className="metric-value num">2</div>
          <div className="metric-sub">Maricopa and Pinal, Arizona</div>
        </div>
      </div>

      <div className="notice" style={{ marginTop: "1rem" }}>
        <strong>
          These two columns are not comparable, and must not be added.
        </strong>{" "}
        {data.note}
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>State</th>
            <th className="num">Reported facilities</th>
            <th className="num">Helios sites</th>
            <th>Coverage</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.state_code}>
              <td className="mono">{row.state_code}</td>
              <td className="num">{row.facility_count.toLocaleString()}</td>
              <td className="num">
                {row.site_count > 0 ? row.site_count : "—"}
              </td>
              <td>
                <span className={coveragePill(row)}>{coverageLabel(row)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="small muted" style={{ marginBottom: 0 }}>
        A dash is not zero data centres. It is zero <em>Helios</em> sites, which
        means no county in that state has been read. Building sites needs parcel
        geometry and ownership, published county by county and often not at all.
      </p>
    </section>
  );
}
