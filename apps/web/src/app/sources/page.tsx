import { ApiUnavailable } from "@/components/ApiUnavailable";
import { StatusPill } from "@/components/AssertionBadge";
import { listSources } from "@/lib/api";
import type { Source } from "@/lib/types";

export const metadata = { title: "Data sources" };

const STATUS_TONE: Record<string, "positive" | "caution" | "neutral"> = {
  implemented: "positive",
  fixture_only: "caution",
  planned: "neutral",
};

export default async function SourcesPage() {
  let sources;
  try {
    sources = await listSources();
  } catch (error) {
    return <ApiUnavailable error={error} />;
  }

  const grouped = groupByCategory(sources.items);

  return (
    <div className="stack container-narrow">
      <div>
        <h1>Data-source registry</h1>
        <p className="muted" style={{ maxWidth: "62ch" }}>
          Every source Helios is permitted to read is declared here before any code fetches
          from it, together with its licence, rate limit, and historical depth. Sources
          Helios <em>cannot</em> read are listed too, with the reason. Publishing the gaps
          is the point: a site with thin evidence may reflect a quiet project or a blocked
          source, and only this page distinguishes them.
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

function SourceEntry({ source }: { source: Source }) {
  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
        <strong>{source.name}</strong>
        <StatusPill tone={STATUS_TONE[source.connector_status ?? "planned"] ?? "neutral"}>
          {(source.connector_status ?? "planned").replace(/_/g, " ")}
        </StatusPill>
        {source.contains_personal_data && (
          <StatusPill
            tone="caution"
            title="This source contains information about private individuals. Helios classifies and redacts it during ingestion."
          >
            Contains personal data
          </StatusPill>
        )}
      </div>

      <dl className="kv" style={{ marginTop: "0.5rem" }}>
        <dt>Agency</dt>
        <dd>{source.agency}</dd>
        <dt>Jurisdiction</dt>
        <dd>{source.jurisdiction}</dd>
        {source.license_name && (
          <>
            <dt>Licence</dt>
            <dd>
              {source.license_url ? (
                <a href={source.license_url} target="_blank" rel="noreferrer">
                  {source.license_name}
                </a>
              ) : (
                source.license_name
              )}
            </dd>
          </>
        )}
        {source.historical_coverage && (
          <>
            <dt>History</dt>
            <dd>{source.historical_coverage}</dd>
          </>
        )}
        {source.document_count > 0 && (
          <>
            <dt>Documents held</dt>
            <dd>{source.document_count}</dd>
          </>
        )}
      </dl>

      {source.access_limitation && (
        <div className="notice" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
          <strong>Access limitation.</strong> {source.access_limitation}
        </div>
      )}

      {source.known_schema_issues && (
        <details style={{ marginTop: "0.5rem" }}>
          <summary>Known schema issues</summary>
          <p className="small muted" style={{ marginTop: "0.35rem" }}>
            {source.known_schema_issues}
          </p>
        </details>
      )}
    </div>
  );
}

function groupByCategory(items: Source[]): Record<string, Source[]> {
  return items.reduce<Record<string, Source[]>>((accumulator, source) => {
    (accumulator[source.category] ??= []).push(source);
    return accumulator;
  }, {});
}
