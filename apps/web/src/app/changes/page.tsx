/**
 * What has appeared on the map, and what has come off it.
 *
 * The wording here is the whole point. An entry that vanishes from
 * OpenStreetMap has been *removed from the map*, which is not the same as
 * demolished: ohsome reports a deletion whenever an element stops matching the
 * data-centre filter, and a mapper retagging `building=data_center` to
 * `building=yes` is indistinguishable from a building coming down. Nothing on
 * this page says "closed" or "demolished", and nothing should.
 *
 * Appearances are usually named and removals usually are not, because names are
 * read from the current snapshot and a removed facility is no longer in it.
 * That asymmetry is left visible rather than papered over with a placeholder
 * that would imply the name was never recorded.
 */
import type { Metadata } from "next";

import { getChanges, getObservatoryMeta } from "@/lib/observatory";
import { ScrollArea } from "@/components/ScrollArea";

export const metadata: Metadata = {
  title: "Changes",
  description:
    "Data centres that recently appeared in or were removed from OpenStreetMap, with the date each edit was made.",
};

export default async function ChangesPage() {
  const [changes, meta] = await Promise.all([
    getChanges(),
    getObservatoryMeta(),
  ]);

  const appeared = changes.filter((c) => c.kind === "creation");
  const removed = changes.filter((c) => c.kind === "deletion");
  const latest = changes[0]?.date;

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>Changes</h1>
          <p className="muted small" style={{ margin: 0 }}>
            The {changes.length.toLocaleString()} most recent times a data
            centre appeared in or was removed from OpenStreetMap
            {latest ? `, through ${latest}` : ""}.
          </p>
        </div>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Appeared</div>
          <div className="metric-value num">
            {appeared.length.toLocaleString()}
          </div>
          <div className="metric-sub">in this window</div>
        </div>
        <div className="metric">
          <div className="metric-label">Removed from OSM</div>
          <div className="metric-value num">
            {removed.length.toLocaleString()}
          </div>
          <div className="metric-sub">not necessarily demolished</div>
        </div>
        <div className="metric">
          <div className="metric-label">Currently mapped</div>
          <div className="metric-value num">
            {meta.facility_count.toLocaleString()}
          </div>
          <div className="metric-sub">across the United States</div>
        </div>
        <div className="metric">
          <div className="metric-label">Latest edit</div>
          <div className="metric-value num" style={{ fontSize: "1.1rem" }}>
            {latest ?? "—"}
          </div>
          <div className="metric-sub">in the history extract</div>
        </div>
      </div>

      <div className="notice">
        <strong>A removal is not a demolition.</strong> OpenStreetMap reports a
        deletion when an element stops matching the data-centre filter. That
        happens when a building genuinely leaves the map, and equally when a
        contributor retags it. This page can tell you the map changed; it cannot
        tell you the world did.
      </div>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Recent edits</h2>
          <span className="card-note">newest first</span>
        </div>
        <ScrollArea className="table-scroll" label="Recent edits, scrollable">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Change</th>
                <th>Facility</th>
                <th>Where</th>
                <th>OSM id</th>
              </tr>
            </thead>
            <tbody>
              {changes.slice(0, 200).map((change) => (
                <tr key={`${change.id}-${change.date}-${change.kind}`}>
                  <td className="mono small">{change.date}</td>
                  <td>
                    <span
                      className={
                        change.kind === "creation"
                          ? "pill pill-positive"
                          : "pill pill-caution"
                      }
                    >
                      {change.kind === "creation"
                        ? "appeared"
                        : "removed from OSM"}
                    </span>
                  </td>
                  <td>
                    {change.name || (
                      <span className="muted">no longer on the map</span>
                    )}
                  </td>
                  <td className="small">
                    {change.county_name || change.state || (
                      <span className="muted">not placed</span>
                    )}
                  </td>
                  <td className="mono small">
                    <a
                      href={`https://www.openstreetmap.org/${change.id}`}
                      rel="noreferrer noopener"
                      target="_blank"
                    >
                      {change.id}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
        <p className="small muted" style={{ marginBottom: 0 }}>
          Every row links to the element on openstreetmap.org, where its full
          edit history is public. Dates are when the edit was made, not when
          anything was built.
        </p>
      </section>
    </div>
  );
}
