import Link from "next/link";
import { GrowthChart } from "@/components/GrowthChart";
import {
  getDetectionLag,
  getStageDistribution,
  getStageGrowth,
  getProvenanceCompleteness,
} from "@/lib/api";

function formatDays(days: number | null): string {
  if (days === null) return "—";
  const years = days / 365.25;
  return years >= 2 ? `${days.toLocaleString()} (~${years.toFixed(1)} yr)` : days.toLocaleString();
}

export default async function AnalyticsPage() {
  const [stages, provenance, growth, lag] = await Promise.all([
    getStageDistribution(),
    getProvenanceCompleteness(),
    getStageGrowth(),
    getDetectionLag(),
  ]);

  // Stage banding is only meaningful once sites accumulate more than one
  // transition each. Until then a per-stage chart is eight identical curves.
  const transitionsPerSite =
    growth.points.length > 0
      ? lag.transitions / growth.points[growth.points.length - 1].sites_tracked
      : 0;
  const progressionObservable = transitionsPerSite > 1.05;

  return (
    <div className="stack">
      <header className="hero">
        <p className="eyebrow">Measured, not asserted</p>
        <h1>Regional analytics</h1>
        <p className="tagline">
          Pipeline coverage and data-quality metrics for{" "}
          {stages.region_slug ?? "all regions"}, including the two numbers Helios owes
          about itself: how complete its provenance is, and how long it takes to notice.
        </p>
      </header>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Sites tracked over time</h2>
          <span className="card-note">{growth.points.length} months with activity</span>
        </div>
        <GrowthChart points={growth.points} />
        {!progressionObservable && (
          <div className="notice" style={{ marginTop: "1rem", marginBottom: 0 }}>
            <strong>Stage progression is not yet observable.</strong> Every site in this
            corpus carries exactly one recorded stage transition, straight to its current
            stage, so a per-stage breakdown would draw one curve per stage and they would
            all be identical. This chart therefore counts sites, not progressions. It
            gains a stage dimension when the pipeline has watched projects actually move.
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Detection lag</h2>
          <span className="card-note">{lag.transitions} transitions measured</span>
        </div>
        <div className="grid grid-4">
          <div className="metric">
            <div className="metric-label">Median lag</div>
            <div className="metric-value num">{formatDays(lag.median_lag_days)}</div>
            <div className="metric-sub">days between evidence and detection</div>
          </div>
          <div className="metric">
            <div className="metric-label">90th percentile</div>
            <div className="metric-value num">{formatDays(lag.p90_lag_days)}</div>
            <div className="metric-sub">the slow tail</div>
          </div>
          <div className="metric">
            <div className="metric-label">Fastest</div>
            <div className="metric-value num">{formatDays(lag.min_lag_days)}</div>
            <div className="metric-sub">same-day at best</div>
          </div>
          <div className="metric">
            <div className="metric-label">Slowest</div>
            <div className="metric-value num">{formatDays(lag.max_lag_days)}</div>
            <div className="metric-sub">oldest record reached back to</div>
          </div>
        </div>
        <div className="notice" style={{ marginTop: "1rem", marginBottom: 0 }}>
          <strong>These are not operating characteristics.</strong> {lag.note} A median
          measured in years reflects Helios reaching back over historical records in a
          single pass, not the delay a live deployment would show. The figure becomes
          meaningful only once the pipeline has been running against changing records
          over time.
        </div>
      </section>

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
