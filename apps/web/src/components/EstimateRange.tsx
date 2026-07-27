/**
 * Renders a ranged estimate as a range.
 *
 * Power and water are the weakest numbers Helios publishes. Showing only the
 * likely value — which is what this interface did — turns a wide band into what
 * looks like a measurement, which is the exact error the assertion vocabulary
 * exists to prevent, committed by the renderer instead of by the data.
 *
 * The band is drawn to scale so that "we barely know" is legible at a glance
 * rather than only on inspection, and the coefficients are one disclosure away
 * so the estimate can be argued with rather than merely believed.
 */
import { AssertionBadge } from "@/components/AssertionBadge";
import type { Estimate } from "@/lib/types";

function format(value: number, unit: string): string {
  // GPD figures run to the hundreds of thousands; MW rarely past four digits.
  const rounded = unit === "GPD" ? Math.round(value) : Math.round(value * 10) / 10;
  return rounded.toLocaleString("en-US");
}

/** Assumption keys that restate the range itself rather than explaining it. */
const REDUNDANT_KEYS = new Set([
  "power_mw_lower",
  "power_mw_likely",
  "power_mw_upper",
]);

function humanise(key: string): string {
  return key.replace(/_/g, " ").replace(/\bmw\b/gi, "MW").replace(/\bgal\b/gi, "gal");
}

export function EstimateRange({ estimate, label }: { estimate: Estimate; label: string }) {
  const { lower_value: lower, likely_value: likely, upper_value: upper, unit } = estimate;

  if (likely === null) {
    return (
      <div className="estimate">
        <div className="estimate-head">
          <span className="estimate-label">{label}</span>
          <AssertionBadge assertion="unknown" />
        </div>
        <p className="estimate-none">Not established.</p>
      </div>
    );
  }

  const hasBand = lower !== null && upper !== null && upper > lower;
  // Where the likely value sits within its own band, as a percentage. Rarely the
  // midpoint: the power band is skewed because 2 MW/acre sits low in a 1-4 range.
  const likelyOffset = hasBand ? ((likely - lower) / (upper - lower)) * 100 : 50;

  const note = typeof estimate.assumptions.note === "string" ? estimate.assumptions.note : null;
  const coefficients = Object.entries(estimate.assumptions).filter(
    ([key]) => key !== "note" && !REDUNDANT_KEYS.has(key),
  );

  return (
    <div className="estimate">
      <div className="estimate-head">
        <span className="estimate-label">{label}</span>
        <AssertionBadge assertion={estimate.assertion_class} />
      </div>

      <p className="estimate-value">
        <strong className="num">{format(likely, unit)}</strong> <span>{unit}</span>
      </p>

      {hasBand && (
        <>
          <div
            className="estimate-band"
            role="img"
            aria-label={`Range ${format(lower, unit)} to ${format(upper, unit)} ${unit}, likely ${format(likely, unit)}`}
          >
            <span className="estimate-band-marker" style={{ left: `${likelyOffset}%` }} />
          </div>
          <p className="estimate-bounds">
            <span className="num">{format(lower, unit)}</span>
            <span className="estimate-bounds-sep">plausible range</span>
            <span className="num">{format(upper, unit)}</span>
          </p>
        </>
      )}

      <p className="estimate-method">{estimate.method}.</p>

      {(note || coefficients.length > 0) && (
        <details className="estimate-assumptions">
          <summary>What this assumes</summary>
          {note && <p className="estimate-note">{note}</p>}
          {coefficients.length > 0 && (
            <dl className="kv">
              {coefficients.map(([key, value]) => (
                <div key={key} className="estimate-assumption-row">
                  <dt>{humanise(key)}</dt>
                  <dd className="num">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </details>
      )}
    </div>
  );
}
