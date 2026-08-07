import { ApiUnavailable } from "@/components/ApiUnavailable";
import { SourceEntry } from "@/components/SourceEntry";
import { StatusPill } from "@/components/AssertionBadge";
import { listRegions, listSources } from "@/lib/api";
import type { Source } from "@/lib/types";
import { routeMeta } from "@/lib/site";

export const metadata = {
  title: "Data sources",
  ...routeMeta("/sources/"),
};

export default async function SourcesPage() {
  let sources;
  let regions;
  try {
    [sources, regions] = await Promise.all([listSources(), listRegions()]);
  } catch (error) {
    return <ApiUnavailable error={error} />;
  }

  const grouped = groupByCategory(sources.items);

  return (
    <div className="stack container-narrow">
      <div>
        <h1>Data-source registry</h1>
        <p className="muted" style={{ maxWidth: "62ch" }}>
          Every source Helios is permitted to read is declared here before any
          code fetches from it, together with its licence, rate limit, and
          historical depth. The sources Helios <em>cannot</em> read are listed
          too, each with the reason. The gaps are published deliberately: a site
          with thin evidence might be a quiet project or a blocked source, and
          this is the only page that tells the two apart.
        </p>
      </div>

      <div className="grid grid-3">
        {Object.entries(sources.coverage_summary).map(([status, count]) => (
          <div className="metric" key={status}>
            <div className="metric-label">{status.replace(/_/g, " ")}</div>
            <div className="metric-value">{count}</div>
          </div>
        ))}
      </div>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Geographic coverage</h2>
          <span className="card-note">
            {regions.active_count} of {regions.items.length} regions read
          </span>
        </div>
        <p className="small muted" style={{ marginTop: 0 }}>
          {regions.note}
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>Region</th>
              <th>Counties</th>
              <th>Coverage</th>
              <th className="num">Sites</th>
            </tr>
          </thead>
          <tbody>
            {regions.items.map((region) => (
              <tr key={region.slug}>
                <td>
                  <strong>{region.name}</strong>
                  <div className="small muted">{region.note}</div>
                </td>
                <td className="small">{region.counties.join(", ")}</td>
                <td>
                  <StatusPill
                    tone={region.coverage === "active" ? "positive" : "neutral"}
                  >
                    {region.coverage}
                  </StatusPill>
                </td>
                <td className="num">{region.site_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {Object.entries(grouped).map(([category, items]) => (
        <section key={category} className="card">
          <h2 className="card-title" style={{ textTransform: "capitalize" }}>
            {category.replace(/_/g, " ")}
          </h2>
          <div className="stack">
            {items.map((source) => (
              <SourceEntry key={source.id} source={source} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function groupByCategory(items: Source[]): Record<string, Source[]> {
  return items.reduce<Record<string, Source[]>>((accumulator, source) => {
    (accumulator[source.category] ??= []).push(source);
    return accumulator;
  }, {});
}
