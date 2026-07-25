import Link from "next/link";

import { Metric } from "@/components/ScoreExplanation";
import { AssertionBadge, ConfidenceBadge } from "@/components/AssertionBadge";
import {
  getProvenanceCompleteness,
  getStageDistribution,
  listSites,
  listSources,
} from "@/lib/api";
import { ApiUnavailable } from "@/components/ApiUnavailable";

export const dynamic = "force-dynamic";

export default async function ObservatoryHome() {
  let data;
  try {
    const [sites, stages, provenance, sources] = await Promise.all([
      listSites({ limit: 8, sort: "-confidence" }),
      getStageDistribution(),
      getProvenanceCompleteness(),
      listSources(),
    ]);
    data = { sites, stages, provenance, sources };
  } catch (error) {
    return <ApiUnavailable error={error} />;
  }

  const { sites, stages, provenance, sources } = data;
  const activeStages = stages.stages.filter((s) => s.site_count > 0);
  const blockedSources = sources.items.filter(
    (s) => s.connector_status !== "implemented",
  );

  return (
    <div className="stack">
      <section>
        <h1>From permit to power-on</h1>
        <p style={{ maxWidth: "62ch", color: "var(--text-muted)" }}>
          Helios assembles fragmented public records into an evidence-backed view of how
          data-centre projects progress through land assembly, permitting, construction,
          grid connection, and operation. Every figure below traces back to a source
          document you can open and verify.
        </p>
      </section>

      <div className="grid grid-4">
        <Metric
          label="Sites tracked"
          value={String(stages.total_sites)}
          sub="East Valley, Arizona"
        />
        <Metric
          label="Evidence records"
          value={String(provenance.total_evidence_records)}
          sub={`${(provenance.completeness_ratio * 100).toFixed(0)}% with complete provenance`}
        />
        <Metric
          label="Sources declared"
          value={String(sources.items.length)}
          sub={`${sources.coverage_summary.implemented ?? 0} with working connectors`}
        />
        <Metric
          label="Coverage gaps"
          value={String(blockedSources.length)}
          sub="declared but not yet ingesting"
        />
      </div>

      <div className="notice">
        <strong>How to read this observatory.</strong> A confidence score is model output,
        not a probability that a facility exists. Helios never names an operator without a
        direct filing, so most sites show <em>Operator not established</em> even when the
        land is plainly in use. Absence of evidence is not evidence of absence: the{" "}
        <Link href="/sources">data-source registry</Link> lists which records Helios cannot
        currently read and why.
      </div>

      <div className="split">
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Highest-confidence sites</h2>
            <Link href="/sites" className="small">
              View all sites &rarr;
            </Link>
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>Project</th>
                <th>City</th>
                <th>Stage</th>
                <th className="num">Acres</th>
                <th className="num">Evidence</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {sites.items.map((site) => (
                <tr key={site.id}>
                  <td>
                    <Link href={`/sites/${site.id}`} className="mono">
                      {site.project_code}
                    </Link>
                  </td>
                  <td>{site.jurisdiction ?? "—"}</td>
                  <td>
                    {site.current_stage_label}{" "}
                    <AssertionBadge assertion={site.site_kind_assertion} />
                  </td>
                  <td className="num">
                    {site.total_acres ? site.total_acres.toFixed(1) : "—"}
                  </td>
                  <td className="num">{site.evidence_count}</td>
                  <td>
                    <ConfidenceBadge
                      confidence={site.current_confidence}
                      band={site.confidence_band}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Development stage distribution</h2>
          </div>
          {activeStages.length === 0 ? (
            <p className="muted">No sites have been classified yet.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th className="num">Sites</th>
                  <th className="num">Mean confidence</th>
                </tr>
              </thead>
              <tbody>
                {activeStages.map((stage) => (
                  <tr key={stage.stage}>
                    <td>
                      <span className="mono muted">{stage.stage}</span> {stage.stage_label}
                    </td>
                    <td className="num">{stage.site_count}</td>
                    <td className="num">
                      {stage.mean_confidence !== null
                        ? `${stage.mean_confidence.toFixed(0)}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="card-note">
            Current coverage is concentrated at Stage 7 because the assessor&rsquo;s
            data-centre classification is applied to facilities that already exist. Earlier
            stages depend on planning and utility filings, which are the sources Helios
            cannot yet read automatically.
          </p>
        </section>
      </div>
    </div>
  );
}
