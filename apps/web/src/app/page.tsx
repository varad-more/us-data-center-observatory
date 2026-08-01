/**
 * The front door.
 *
 * This page has one job: tell a reader who has never seen Helios what is here,
 * what kind of claim each number is, and where to go next. It leads with the
 * national observatory because that is the larger and more general dataset —
 * 1,853 facilities across the country — and treats the Arizona site model as
 * what it is, a second and much deeper study of one valley.
 *
 * The two halves are kept visually and verbally separate. They answer different
 * questions from different evidence: the observatory reports where data centres
 * have been *mapped*, while the Arizona model argues, from parcel and permit
 * records, where one is probably *being built*. Merging them into a single
 * headline figure would blur a reported count into an inferred one, which is
 * the failure this project exists to avoid.
 *
 * The Arizona half is loaded defensively. It comes from the exported API
 * payloads, and when those are absent — a fresh checkout, a partial export —
 * the observatory must still render. Before, a missing API replaced the entire
 * page with an error, including all the content that never needed it.
 */
import Link from "next/link";

import { AssertionBadge } from "@/components/AssertionBadge";
import { MappingGrowthChart } from "@/components/MappingGrowthChart";
import { getStageDistribution, listSites } from "@/lib/api";
import {
  getChanges,
  getNationalEnergy,
  getNationalSeries,
  getObservatoryMeta,
  getRegions,
  regionSlug,
} from "@/lib/observatory";

/** How many of the densest counties the front page names before deferring. */
const TOP_COUNTIES = 8;

/** How many recent map edits the front page shows before deferring. */
const RECENT_CHANGES = 6;

interface ArizonaSummary {
  siteCount: number;
  topCode: string | null;
  topStage: string | null;
}

/**
 * The Arizona study, or null when its payloads are not present.
 *
 * Returning null rather than throwing is deliberate: this dataset is a section
 * of the page, not the page, and its absence should cost the reader that
 * section and nothing else.
 */
async function loadArizona(): Promise<ArizonaSummary | null> {
  try {
    const [sites, stages] = await Promise.all([
      listSites({ limit: 1, sort: "-confidence" }),
      getStageDistribution(),
    ]);
    const top = sites.items[0];
    return {
      siteCount: stages.total_sites,
      topCode: top?.project_code ?? null,
      topStage: top?.current_stage_label ?? null,
    };
  } catch {
    return null;
  }
}

export default async function Home() {
  const [meta, regions, series, energy, changes, arizona] = await Promise.all([
    getObservatoryMeta(),
    getRegions(),
    getNationalSeries(),
    getNationalEnergy(),
    getChanges(),
    loadArizona(),
  ]);

  const counties = regions.filter((r) => r.kind === "county");
  const states = regions.filter((r) => r.kind === "state");
  const topCounties = [...counties]
    .sort((a, b) => b.facility_count - a.facility_count)
    .slice(0, TOP_COUNTIES);

  // Net movement over the last twelve months of the series. Net rather than
  // gross: removals are real edits and hiding them would overstate arrivals.
  const recentPoints = series?.points.slice(-12) ?? [];
  const netYear = recentPoints.reduce((sum, point) => sum + point.change, 0);

  const historical = energy.filter((p) => p.series_kind === "historical");
  const latestPower = [...historical]
    .filter((p) => p.electricity_twh !== null)
    .sort((a, b) => b.year - a.year)[0];
  const latestWater = [...historical]
    .filter((p) => p.water_bgal !== null)
    .sort((a, b) => b.year - a.year)[0];
  const earliestPower = [...historical]
    .filter((p) => p.electricity_twh !== null)
    .sort((a, b) => a.year - b.year)[0];
  const outlook = energy.find(
    (p) => p.series_kind === "projection" && p.year === 2030 && p.scenario === "reference",
  );

  // The year the plotted curve actually starts, read off the series itself.
  // A typed year here said 2012, which is where the ohsome query window opens,
  // not where the data does - the first observed edit is 2015-07. The heading
  // and the chart's own aria-label consequently gave a reader and a screen
  // reader two different ranges for the same picture.
  const seriesFrom = series?.points[0]?.period.slice(0, 4) ?? null;

  // Derived rather than typed, so it cannot drift from the figures beside it
  // when a new LBNL year is added to the CSV.
  const growthMultiple =
    latestPower?.electricity_twh && earliestPower?.electricity_twh
      ? latestPower.electricity_twh / earliestPower.electricity_twh
      : null;

  return (
    <div className="stack">
      <section className="hero">
        <p className="eyebrow">United States · OpenStreetMap · Lawrence Berkeley Lab</p>
        <h1>Where data centres are, and how fast they are arriving</h1>
        <p className="tagline">
          Helios tracks {meta.facility_count.toLocaleString()} data centres across the
          United States, each at a real coordinate and each traceable to the public
          record it came from. It plots how that number has grown, county by county,
          against the electricity and water the country is reported to spend on them.
        </p>
        <div className="button-row" style={{ marginTop: "1rem" }}>
          <Link className="button button-primary" href="/growth">
            See the growth curve
          </Link>
          <Link className="button" href="/regions">
            Find a county
          </Link>
          <Link className="button" href="/understand">
            New here? Start with the basics
          </Link>
        </div>
      </section>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Data centres mapped</div>
          <div className="metric-value num">{meta.facility_count.toLocaleString()}</div>
          <div className="metric-sub">reported by OSM contributors</div>
        </div>
        <div className="metric">
          <div className="metric-label">Counties holding one</div>
          <div className="metric-value num">{counties.length}</div>
          <div className="metric-sub">across {states.length} states</div>
        </div>
        <div className="metric">
          <div className="metric-label">Net change, 12 months</div>
          <div className="metric-value num">
            {netYear >= 0 ? "+" : ""}
            {netYear.toLocaleString()}
          </div>
          <div className="metric-sub">appeared minus removed</div>
        </div>
        <div className="metric">
          <div className="metric-label">US data-centre power</div>
          <div className="metric-value num">
            {latestPower ? latestPower.electricity_twh?.toLocaleString() : "—"}
          </div>
          <div className="metric-sub">
            TWh in {latestPower?.year ?? "—"}, reported by LBNL
          </div>
        </div>
      </div>

      <div className="notice">
        <strong>Three kinds of number appear on this site, and they are not
        interchangeable.</strong>{" "}
        A location is <AssertionBadge assertion="reported" />: a contributor mapped it.
        A date is <em>observed</em>, meaning the month OpenStreetMap first recorded the
        facility. Never the month it was built, because OpenStreetMap carries no
        construction dates. A megawatt figure is <AssertionBadge assertion="inferred" />,
        a share of a national total published by Lawrence Berkeley National Laboratory
        and divided up by building floor area. Only facilities mapped as buildings get
        one, never a campus land parcel and never a site still under construction.{" "}
        <Link href="/understand">What each of these means</Link>.
      </div>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">
            Data centres on the map{seriesFrom ? `, ${seriesFrom} to today` : ""}
          </h2>
          <Link href="/growth" className="small">
            Full series and national energy &rarr;
          </Link>
        </div>
        {series ? (
          <MappingGrowthChart points={series.points} />
        ) : (
          <p className="muted small">
            The growth series has not been built yet. Run{" "}
            <code>make poll</code> to produce it.
          </p>
        )}
      </section>

      <div className="split">
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Where they concentrate</h2>
            <Link href="/regions" className="small">
              All {regions.length} regions &rarr;
            </Link>
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>County</th>
                  <th className="num">Mapped</th>
                  <th className="num">Floor area km²</th>
                  <th className="num">Share MW</th>
                </tr>
              </thead>
              <tbody>
                {topCounties.map((county) => (
                  <tr key={county.region_id}>
                    <td>
                      <Link href={`/regions/${regionSlug(county.region_id)}`}>
                        {county.name}
                      </Link>
                      <span className="muted small">, {county.state}</span>
                    </td>
                    <td className="num">{county.facility_count.toLocaleString()}</td>
                    <td className="num">{(county.footprint_m2 / 1e6).toFixed(2)}</td>
                    <td className="num">{Math.round(county.est_mw).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="card-note">
            The densest county here holds more mapped data centres than most states.
            Megawatt figures are inferred shares of a reported national total, not meter
            readings.
          </p>
        </section>

        <section className="card">
          <div className="card-header">
            <h2 className="card-title">What changed lately</h2>
            <Link href="/changes" className="small">
              Full feed &rarr;
            </Link>
          </div>
          {changes.length === 0 ? (
            <p className="muted small">No change history has been built yet.</p>
          ) : (
            <ul className="feed">
              {changes.slice(0, RECENT_CHANGES).map((change) => (
                <li key={`${change.id}-${change.date}-${change.kind}`}>
                  <span className="mono small muted">{change.date}</span>{" "}
                  <span
                    className={
                      change.kind === "creation" ? "pill pill-positive" : "pill pill-caution"
                    }
                  >
                    {change.kind === "creation" ? "appeared" : "removed from OSM"}
                  </span>
                  <div className="small">
                    {change.name || <span className="muted">unnamed</span>}
                    {change.county_name ? (
                      <span className="muted"> · {change.county_name}</span>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="card-note">
            A removal means the element stopped matching the data-centre filter in
            OpenStreetMap. That is not the same as a demolition, and this site never
            claims it is.
          </p>
        </section>
      </div>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">The national picture these counts sit inside</h2>
          <Link href="/growth" className="small">
            Every published figure &rarr;
          </Link>
        </div>
        <div className="grid grid-3">
          <div>
            <div className="metric-label">Electricity</div>
            <p className="small" style={{ marginBottom: 0 }}>
              US data centres consumed{" "}
              <strong>{latestPower?.electricity_twh?.toLocaleString()} TWh</strong> in{" "}
              {latestPower?.year}
              {growthMultiple && earliestPower
                ? ` — ${growthMultiple.toFixed(1)}× the ${earliestPower.electricity_twh} TWh they used in ${earliestPower.year}`
                : ""}
              . For scale, that is a few per cent of all the electricity consumed in the
              country.
            </p>
          </div>
          <div>
            <div className="metric-label">Water</div>
            <p className="small" style={{ marginBottom: 0 }}>
              Cooling them consumed{" "}
              <strong>{latestWater?.water_bgal} billion gallons</strong> directly in{" "}
              {latestWater?.year}, before counting the water spent generating the
              electricity itself.
            </p>
          </div>
          <div>
            <div className="metric-label">Outlook</div>
            <p className="small" style={{ marginBottom: 0 }}>
              LBNL&apos;s reference case puts {outlook?.year} at{" "}
              <strong>{outlook?.electricity_twh?.toLocaleString()} TWh</strong>. That is a{" "}
              <AssertionBadge assertion="predicted" /> figure: a scenario, not a
              measurement. LBNL publishes it as a range, and so does this site.
            </p>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Start here</h2>
          <span className="card-note">what each part of the site answers</span>
        </div>
        <div className="guide-grid">
          <Link href="/understand" className="guide-card">
            <h3>The basics</h3>
            <p>
              What a data centre actually contains, why electricity is the constraint that
              decides where one gets built, why cooling spends water, and what every unit
              on this site means.
            </p>
          </Link>
          <Link href="/growth" className="guide-card">
            <h3>Growth over time</h3>
            <p>
              How many data centres the map has recorded each month, beside the national
              electricity and water totals — and why the two series must never be divided
              into each other.
            </p>
          </Link>
          <Link href="/regions" className="guide-card">
            <h3>Regions</h3>
            <p>
              Every county and state holding at least one mapped facility, sortable by
              count, floor area or allocated load. Each has its own page and its own curve.
            </p>
          </Link>
          <Link href="/construction" className="guide-card">
            <h3>Mapped construction</h3>
            <p>
              The {meta.construction_count?.toLocaleString() ?? "—"} records contributors
              currently mark as under construction — a forward signal kept separate from
              operating power and water estimates.
            </p>
          </Link>
          <Link href="/large-load-filings" className="guide-card">
            <h3>Large-load filings</h3>
            <p>
              Site-specific utility-regulator decisions that report a contracted
              electricity load, kept separate from operating consumption and mapped
              only at the precision the filing supports.
            </p>
          </Link>
          <Link href="/observatory-map" className="guide-card">
            <h3>The national map</h3>
            <p>
              All {meta.facility_count.toLocaleString()} facilities at their mapped
              coordinates. Building circles scale by floor plate; campus boundaries and
              construction records stay fixed-size so land area cannot masquerade as
              building area.
            </p>
          </Link>
          <Link href="/changes" className="guide-card">
            <h3>Changes</h3>
            <p>
              What appeared on the map and what came off it, newest first, every row
              linking to the OpenStreetMap element so you can check the edit yourself.
            </p>
          </Link>
          <Link href="/methodology" className="guide-card">
            <h3>How it was built</h3>
            <p>
              The pipeline end to end — where each figure comes from, how the power
              allocation works, and the list of things this dataset cannot see.
            </p>
          </Link>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">A second, deeper dataset: the Arizona study</h2>
          {arizona ? (
            <Link href="/sites" className="small">
              Browse the site register &rarr;
            </Link>
          ) : null}
        </div>
        <p className="small">
          Everything above is a map of what has already been <em>recorded</em>. It cannot
          see a project before someone maps it, and in practice nobody maps a data centre
          until the building is standing. The Arizona study is the opposite experiment. In
          one valley in Maricopa County, Helios reads parcel transfers, permits, assessor
          classifications and utility filings, clusters them into candidate sites, and
          argues a confidence score for each with the evidence chain attached.
        </p>
        {arizona ? (
          <>
            <p className="small">
              It currently tracks <strong>{arizona.siteCount}</strong> candidate sites.
              Every point of every score links back to the document that produced it, and
              an operator is never named without a direct filing.
              {arizona.topCode ? (
                <>
                  {" "}
                  The highest-confidence site is{" "}
                  <Link href={`/sites/${arizona.topCode}`} className="mono">
                    {arizona.topCode}
                  </Link>
                  {arizona.topStage ? `, at ${arizona.topStage.toLowerCase()}` : ""}.
                </>
              ) : null}
            </p>
            <div className="button-row">
              <Link className="button" href="/sites">
                Site register
              </Link>
              <Link className="button" href="/map">
                Arizona parcel map
              </Link>
              <Link className="button" href="/analytics">
                Model analytics
              </Link>
            </div>
          </>
        ) : (
          <p className="small muted" style={{ marginBottom: 0 }}>
            The Arizona payloads are not present in this build, so its figures are omitted
            rather than estimated. Run <code>make export-static-api</code> to generate
            them.
          </p>
        )}
      </section>
    </div>
  );
}
