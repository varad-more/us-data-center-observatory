/**
 * The region's measured resource totals, and Helios's sites set against them.
 *
 * Everything else on this site is something Helios worked out. These totals are
 * not: an agency measured them and published them. That makes this the one
 * place where the badge on the number is doing the opposite of its usual job —
 * marking a figure as stronger than its neighbours rather than weaker.
 *
 * The two halves stay visually separate for the same reason the API returns
 * them as separate lists. A reported county withdrawal and an inferred site
 * estimate must never sit in one column where a reader could sum them.
 */
import { AssertionBadge } from "@/components/AssertionBadge";
import type { AreaConsumption, AreaTotal, HeliosShare } from "@/lib/types";

const METRIC_LABELS: Record<string, string> = {
  public_supply_water_withdrawal: "Public supply water",
  industrial_water_withdrawal: "Industrial water",
  thermoelectric_water_withdrawal: "Thermoelectric water",
  total_water_withdrawal: "Total water withdrawal",
  electricity_retail_sales: "Retail electricity sales",
  generation_nameplate_capacity: "Generation capacity (nameplate)",
  generation_summer_capacity: "Generation capacity (summer)",
  population: "Population",
};

function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric.replace(/_/g, " ");
}

function format(value: number): string {
  // Withdrawals run from hundredths to a few thousand and the decimals carry
  // real information; electricity sales run to tens of millions where they do
  // not. Rounding 776.54 Mgal/d to 777 would quietly restate a source figure.
  return value.toLocaleString("en-US", {
    maximumFractionDigits: value < 10_000 ? 2 : 0,
  });
}

function formatShare(pct: number | null): string {
  if (pct === null) return "—";
  // Below a hundredth of a percent, two decimals reads as zero and implies a
  // precision the underlying band does not have.
  return pct < 0.01 ? "<0.01%" : `${pct.toFixed(2)}%`;
}

function sectorSuffix(sector: string): string {
  return sector === "all" ? "" : ` (${sector})`;
}

const ROLLUP_SECTORS = new Set(["all", "total"]);

/**
 * Whether a row is a roll-up of other rows actually present beside it.
 *
 * A roll-up sector is only a double-count risk when its parts are on screen
 * too. Water carries sector "all" with no siblings and is just a figure; EIA
 * publishes "total" as one sector among five, where a reader adding the column
 * would count the whole state twice.
 */
function isRollup(row: AreaTotal, all: AreaTotal[]): boolean {
  if (!ROLLUP_SECTORS.has(row.sector)) return false;
  return all.some(
    (other) =>
      other.metric === row.metric &&
      other.area_code === row.area_code &&
      !ROLLUP_SECTORS.has(other.sector),
  );
}

function TotalsTable({ totals }: { totals: AreaTotal[] }) {
  // A roll-up sorts below the parts it rolls up: EIA publishes "total" as one
  // sector among five, so alphabetically it lands mid-column where a reader
  // could plausibly add it in.
  const ordered = [...totals].sort((a, b) => {
    if (a.metric !== b.metric || a.area_code !== b.area_code) return 0;
    return Number(isRollup(a, totals)) - Number(isRollup(b, totals));
  });
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Measure</th>
          <th>Area</th>
          <th className="num">Published figure</th>
          <th className="num">Year</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {ordered.map((total) => (
          <tr key={`${total.area_code}-${total.metric}-${total.sector}`}>
            <td>
              {metricLabel(total.metric)}
              {sectorSuffix(total.sector)}
              {isRollup(total, totals) && (
                <span className="muted small"> — sum of the sectors above</span>
              )}
            </td>
            <td className="small">
              {total.area_name}
              <span className="muted"> · {total.area_kind}</span>
            </td>
            <td className="num">
              {format(total.value)} <span className="muted small">{total.unit}</span>
            </td>
            <td className="num">{total.reference_year}</td>
            <td className="small muted">{total.source_name}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Comparison({ share }: { share: HeliosShare }) {
  // Where the likely figure sits inside its own band, drawn to scale so a wide
  // band reads as uncertainty rather than as a decorative bar.
  const span = share.inferred_upper - share.inferred_lower;
  const offset =
    span > 0 ? ((share.inferred_likely - share.inferred_lower) / span) * 100 : 50;

  const note = typeof share.assumptions.note === "string" ? share.assumptions.note : null;

  return (
    <div className="estimate">
      <div className="estimate-head">
        <span className="estimate-label">{metricLabel(share.metric)}</span>
        <AssertionBadge assertion="inferred" />
      </div>

      <p className="estimate-value">
        <strong className="num">{formatShare(share.share_likely_pct)}</strong>{" "}
        <span>
          of {share.area_name}&rsquo;s {format(share.area_value)} {share.unit} (
          {share.area_reference_year})
        </span>
      </p>

      {span > 0 && (
        <>
          <div
            className="estimate-band"
            role="img"
            aria-label={`Range ${formatShare(share.share_lower_pct)} to ${formatShare(
              share.share_upper_pct,
            )}, likely ${formatShare(share.share_likely_pct)}`}
          >
            <span className="estimate-band-marker" style={{ left: `${offset}%` }} />
          </div>
          <p className="estimate-bounds">
            <span className="num">{formatShare(share.share_lower_pct)}</span>
            <span className="estimate-bounds-sep">plausible range</span>
            <span className="num">{formatShare(share.share_upper_pct)}</span>
          </p>
        </>
      )}

      <p className="estimate-method">
        {share.sites_counted} site{share.sites_counted === 1 ? "" : "s"} totalling{" "}
        <span className="num">{format(share.inferred_likely)}</span> {share.unit}.{" "}
        {share.method}.
      </p>

      <details className="estimate-assumptions">
        <summary>What this comparison does and does not show</summary>
        <p className="estimate-note">{share.caveat}</p>
        {note && <p className="estimate-note">{note}</p>}
      </details>
    </div>
  );
}

export function AreaConsumptionPanel({ data }: { data: AreaConsumption }) {
  if (data.totals.length === 0) {
    return (
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Regional consumption</h2>
        </div>
        <div className="notice" style={{ marginBottom: 0 }}>
          <strong>No published totals for {data.region_name}.</strong> Helios has not
          ingested county water or state electricity figures for this region, so its
          per-site estimates here have no measured denominator to sit against.
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">What {data.region_name} already uses and can generate</h2>
          <span className="card-note">
            <AssertionBadge assertion="reported" /> measured and published
          </span>
        </div>
        <p className="small muted" style={{ marginTop: 0 }}>
          {data.note}
        </p>
        <TotalsTable totals={data.totals} />
        <div className="notice" style={{ marginTop: "1rem", marginBottom: 0 }}>
          <strong>Water and electricity cover different areas.</strong>{" "}
          {data.granularity_note}
        </div>
      </section>

      {data.comparisons.length > 0 && (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Helios&rsquo;s sites against those totals</h2>
            <span className="card-note">
              <AssertionBadge assertion="inferred" /> derived from acreage
            </span>
          </div>
          {data.comparisons.map((share) => (
            <Comparison key={share.metric} share={share} />
          ))}
        </section>
      )}
    </>
  );
}
