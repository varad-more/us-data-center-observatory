import { AssertionBadge, StatusPill } from "@/components/AssertionBadge";
import type { LargeLoadFiling } from "@/lib/types";

function label(value: string): string {
  return value.replace(/_/g, " ");
}

export function LargeLoadFilingEntry({
  filing,
}: {
  filing: LargeLoadFiling;
}) {
  const digest = filing.source.content_sha256.slice(0, 12);

  return (
    <article className="card">
      <div className="card-header">
        <div>
          <p className="eyebrow">
            {filing.source.agency} · docket {filing.docket_number}
          </p>
          <h2 className="card-title">
            {filing.utility_name} service contract
          </h2>
        </div>
        <StatusPill tone="positive">{label(filing.decision_status)}</StatusPill>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Reported contracted load</div>
          <div className="metric-value num">
            {filing.reported_load_mw.toLocaleString("en-US")} MW
          </div>
          <div className="metric-sub">
            <AssertionBadge assertion={filing.load_assertion_class} />
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Customer in filing</div>
          <div>
            <strong>{filing.customer_name}</strong>
          </div>
          <div className="metric-sub">
            {filing.parent_company_name
              ? `MPSC identifies it as a subsidiary of ${filing.parent_company_name}`
              : "No parent company stated"}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Location stated</div>
          <div>
            <strong>{filing.location_name}</strong>
          </div>
          <div className="metric-sub">
            {filing.county_name}, {filing.state_code}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Decision date</div>
          <div>
            <strong>
              {new Date(`${filing.decision_date}T00:00:00Z`).toLocaleDateString(
                "en-US",
                {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                  timeZone: "UTC",
                },
              )}
            </strong>
          </div>
          <div className="metric-sub">{label(filing.project_type)}</div>
        </div>
      </div>

      <div className="notice" style={{ marginTop: "1rem" }}>
        <strong>Township-level filing record; no site point published.</strong>{" "}
        The regulator names {filing.location_name}, but this record contains no
        parcel evidence or exact geometry. The load is contracted demand reported
        in a regulatory decision—not measured consumption, generating capacity,
        or available grid capacity.
      </div>

      <p>{filing.summary}</p>
      <blockquote className="snippet" style={{ marginInline: 0 }}>
        {filing.snippet}
      </blockquote>
      <div className="provenance">
        <a href={filing.source.source_url} target="_blank" rel="noreferrer">
          Check the official MPSC disclosure
        </a>
        <span>{filing.snippet_locator ?? "decision disclosure"}</span>
        <span className="mono" title={filing.source.content_sha256}>
          SHA-256 {digest}…
        </span>
        <span>
          retrieved{" "}
          {new Date(filing.source.retrieved_at).toLocaleDateString("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
            timeZone: "UTC",
          })}
        </span>
      </div>
    </article>
  );
}
