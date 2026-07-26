import Link from "next/link";
import { getStageDistribution, getProvenanceCompleteness } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const [stages, provenance] = await Promise.all([
    getStageDistribution(),
    getProvenanceCompleteness()
  ]);

  return (
    <div className="stack">
      <header>
        <div className="card-header" style={{ marginBottom: "0.25rem" }}>
          <div>
            <h1 style={{ marginBottom: "0.25rem" }}>Regional Analytics</h1>
            <p className="muted" style={{ margin: 0 }}>
              Pipeline overview and data quality metrics for {stages.region_slug ?? "all regions"}
            </p>
          </div>
        </div>
      </header>

      <div className="split">
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Development Stages</h2>
            <span className="card-note">{stages.total_sites} total sites</span>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Stage</th>
                <th className="num">Sites</th>
                <th className="num">Mean Confidence</th>
              </tr>
            </thead>
            <tbody>
              {stages.stages.map((s) => (
                <tr key={s.stage}>
                  <td>
                    Stage {s.stage}: {s.stage_label}
                  </td>
                  <td className="num">{s.site_count}</td>
                  <td className="num">
                    {s.mean_confidence !== null ? `${s.mean_confidence.toFixed(1)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Data Quality: Provenance Completeness</h2>
          </div>
          <div className="stack">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>Overall Completeness</strong>
              <span className="mono" style={{ fontSize: "1.5rem" }}>
                {(provenance.completeness_ratio * 100).toFixed(1)}%
              </span>
            </div>
            <p className="small muted" style={{ margin: "0.25rem 0" }}>
              {provenance.note}
            </p>
            <table className="table">
              <tbody>
                <tr>
                  <td>Total Evidence Records</td>
                  <td className="num">{provenance.total_evidence_records}</td>
                </tr>
                <tr>
                  <td>With Document Version</td>
                  <td className="num">{provenance.with_document_version}</td>
                </tr>
                <tr>
                  <td>With Text Snippet</td>
                  <td className="num">{provenance.with_snippet}</td>
                </tr>
                <tr>
                  <td>With Source Locator</td>
                  <td className="num">{provenance.with_locator}</td>
                </tr>
                <tr>
                  <td>With Observation Date</td>
                  <td className="num">{provenance.with_observation_date}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <p className="small muted">
        <Link href="/sites">&larr; Back to all sites</Link>
      </p>
    </div>
  );
}
