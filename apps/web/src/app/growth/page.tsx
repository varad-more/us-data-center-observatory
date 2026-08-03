/**
 * How the mapped stock of data centres has grown, against what the country is
 * reported to consume.
 *
 * Two series sit on this page and they are different kinds of claim. The count
 * is *observed*: a tally of what OpenStreetMap recorded, month by month. The
 * electricity figures are *reported*: Lawrence Berkeley National Laboratory's
 * published national totals. Neither is a measurement of the other, and the
 * page never divides one by the other to manufacture a per-facility trend.
 */
import type { Metadata } from "next";

import { MappingGrowthChart } from "@/components/MappingGrowthChart";
import { NationalEnergyTable } from "@/components/NationalEnergyTable";
import {
  getNationalEnergy,
  getNationalSeries,
  getObservatoryMeta,
} from "@/lib/observatory";

export const metadata: Metadata = {
  title: "Growth",
  description:
    "Data centres recorded in OpenStreetMap over time, beside the reported national electricity and water totals.",
};

export default async function GrowthPage() {
  const [series, energy, meta] = await Promise.all([
    getNationalSeries(),
    getNationalEnergy(),
    getObservatoryMeta(),
  ]);

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>Growth</h1>
          <p className="muted small" style={{ margin: 0 }}>
            What has appeared on the map over time, and what the country is
            reported to consume.
          </p>
        </div>
      </div>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Data centres on the map</h2>
          <span className="card-note">observed, not surveyed</span>
        </div>

        {series ? (
          <MappingGrowthChart points={series.points} />
        ) : (
          <div className="notice">
            <strong>The growth series has not been built yet.</strong> It comes
            from replaying OpenStreetMap&apos;s full edit history through the
            ohsome API, which is a slow, volunteer-run service; the backfill is
            resumable and has not finished. Run{" "}
            <code>python scripts/observatory/fetch_osm_history.py</code>{" "}
            followed by <code>python scripts/observatory/build_series.py</code>{" "}
            to produce it. Nothing is drawn here in the meantime, because a
            partial history would understate every year it touched.
          </div>
        )}
      </section>

      <NationalEnergyTable points={energy} />

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">
            Why these two series must not be divided
          </h2>
        </div>
        <p className="small">
          It is tempting to divide reported national electricity by the mapped
          facility count and call the result the power of an average data
          centre. That number would be meaningless. The numerator covers every
          data centre in the United States; the denominator covers only the{" "}
          {meta.facility_count.toLocaleString()} that OpenStreetMap happens to
          know about. Their ratio measures mapping coverage at least as much as
          it measures anything physical.
        </p>
        <p className="small" style={{ marginBottom: 0 }}>
          The same caution applies to the per-region megawatt figures elsewhere
          on this site. Those allocate the national total across mapped
          facilities by building footprint, so they are shares of a reported
          quantity — and upper bounds, since the facilities nobody has mapped
          have their consumption handed to the ones that have been.
        </p>
      </section>
    </div>
  );
}
