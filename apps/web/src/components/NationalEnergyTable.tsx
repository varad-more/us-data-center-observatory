/**
 * The reported national electricity and water totals, with their provenance.
 *
 * Every row states which of Lawrence Berkeley National Laboratory's reports it
 * came from and whether it is a measured year or a forecast. That distinction
 * carries the weight here: 192 TWh for 2024 is an estimate of something that
 * happened, while 649 TWh for 2030 is a scenario, and the two must not be read
 * off the same line without the label that separates them.
 *
 * Electricity and water also sit on different clocks. The 2025 update carries
 * electricity through 2024; water still rests on the 2024 report's 2023 figure.
 * They are shown as published rather than aligned to a common year, because
 * matching one dataset's staleness to another's is worse than showing the gap.
 */
import type { NationalEnergyPoint } from "@/lib/observatory";

function assertionPill(point: NationalEnergyPoint): string {
  return point.assertion_class === "reported" ? "pill pill-positive" : "pill pill-caution";
}

export function NationalEnergyTable({ points }: { points: NationalEnergyPoint[] }) {
  const historical = points.filter((p) => p.series_kind === "historical");
  const projected = points.filter((p) => p.series_kind === "projection");
  const latest = historical.filter((p) => p.electricity_twh !== null).at(-1);
  const latestWater = historical.filter((p) => p.water_bgal !== null).at(-1);

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">US data-centre electricity and water</h2>
        <span className="card-note">reported by LBNL</span>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Electricity</div>
          <div className="metric-value num">{latest?.electricity_twh ?? "—"}</div>
          <div className="metric-sub">TWh in {latest?.year ?? "—"}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Water</div>
          <div className="metric-value num">{latestWater?.water_bgal ?? "—"}</div>
          <div className="metric-sub">billion gallons in {latestWater?.year ?? "—"}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Growth</div>
          <div className="metric-value num">
            {latest && historical[0]?.electricity_twh
              ? `${(latest.electricity_twh! / historical[0].electricity_twh!).toFixed(1)}×`
              : "—"}
          </div>
          <div className="metric-sub">
            {historical[0]?.year}–{latest?.year}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">2030 forecast</div>
          <div className="metric-value num">
            {projected.find((p) => p.year === 2030 && p.scenario === "reference")
              ?.electricity_twh ?? "—"}
          </div>
          <div className="metric-sub">TWh, reference case</div>
        </div>
      </div>

      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Year</th>
              <th className="num">Electricity TWh</th>
              <th className="num">Water bn gal</th>
              <th>Scenario</th>
              <th>Class</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={`${point.year}-${point.scenario}-${point.source}`}>
                <td className="mono">{point.year}</td>
                <td className="num">{point.electricity_twh ?? "—"}</td>
                <td className="num">{point.water_bgal ?? "—"}</td>
                <td>{point.scenario || (point.series_kind === "historical" ? "—" : "")}</td>
                <td>
                  <span className={assertionPill(point)}>{point.assertion_class}</span>
                </td>
                <td className="small muted">{point.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="small muted" style={{ marginBottom: 0 }}>
        Years without a published figure are absent rather than interpolated. LBNL states
        these particular years as numbers; the gaps between them are not filled in here,
        because a straight line drawn through two real points is not a third real point.
      </p>
    </section>
  );
}
