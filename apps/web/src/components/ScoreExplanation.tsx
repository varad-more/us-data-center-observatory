/**
 * "Why Helios believes this" - the score breakdown.
 *
 * Shows every rule contribution with its arithmetic, so a reader can see not
 * only which evidence mattered but how much its age and extraction confidence
 * discounted it. Negative contributions are shown with equal prominence: a
 * score that only displays supporting evidence is advocacy, not analysis.
 */
import type { Prediction } from "@/lib/types";

export function ScoreExplanation({ prediction }: { prediction: Prediction }) {
  const positive = prediction.explanations.filter((e) => e.applied_weight > 0);
  const negative = prediction.explanations.filter((e) => e.applied_weight < 0);

  return (
    <div className="stack">
      <div className="grid grid-4">
        <Metric
          label="Confidence"
          value={`${prediction.confidence.toFixed(0)}%`}
          sub={prediction.confidence_band.replace("_", " ")}
        />
        <Metric
          label="Supporting weight"
          value={`+${prediction.positive_contribution.toFixed(1)}`}
          sub={`${positive.length} contribution${positive.length === 1 ? "" : "s"}`}
        />
        <Metric
          label="Countervailing weight"
          value={prediction.negative_contribution.toFixed(1)}
          sub={`${negative.length} contribution${negative.length === 1 ? "" : "s"}`}
        />
        <Metric
          label="Evidence diversity"
          value={String(prediction.distinct_evidence_kinds)}
          sub={`distinct kinds across ${prediction.evidence_considered} records`}
        />
      </div>

      <div>
        {prediction.explanations.map((explanation) => (
          <div className="contribution" key={`${explanation.rule_id}-${explanation.evidence_record_id ?? "none"}`}>
            <div
              className={`contribution-weight ${
                explanation.applied_weight >= 0 ? "positive" : "negative"
              }`}
            >
              {explanation.applied_weight >= 0 ? "+" : ""}
              {explanation.applied_weight.toFixed(2)}
            </div>
            <div>
              <div className="contribution-label">{explanation.label}</div>
              {explanation.detail && (
                <div className="contribution-detail">{explanation.detail}</div>
              )}
              <div className="contribution-math">
                base {explanation.base_weight.toFixed(0)} &times; extraction confidence{" "}
                {explanation.confidence_multiplier.toFixed(2)} &times; recency{" "}
                {explanation.recency_multiplier.toFixed(2)}
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="card-note">
        Scored by <code>{prediction.model_name}</code> version{" "}
        <code>{prediction.model_version}</code> on{" "}
        {new Date(prediction.calculated_at).toISOString().slice(0, 10)}, using evidence
        available as of {prediction.as_of_date}. Weights are domain-reasoned starting
        points, not values fitted to outcomes; calibration is deferred until a historical
        backtest exists to calibrate against.
      </p>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}

export { Metric };
