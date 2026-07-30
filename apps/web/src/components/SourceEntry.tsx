import { StatusPill } from "@/components/AssertionBadge";
import type { Source } from "@/lib/types";

const STATUS_TONE: Record<string, "positive" | "caution" | "neutral"> = {
  implemented: "positive",
  fixture_only: "caution",
  planned: "neutral",
  // Withdrawn reads as caution, not neutral: a source the publisher took away
  // is a live gap in coverage, whereas "planned" is merely work not yet done.
  withdrawn: "caution",
};

export function SourceEntry({ source }: { source: Source }) {
  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
        <strong>
          <a href={source.base_url} target="_blank" rel="noreferrer">
            {source.name}
          </a>
        </strong>
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

      {source.notes && (
        <p className="small muted" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
          <strong>Registry note.</strong> {source.notes}
        </p>
      )}

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
