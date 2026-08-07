/**
 * The front page, as a strip-chart recorder.
 *
 * Why this form and not a dashboard: the one thing this project must never do
 * is let an absence render as a zero, and a chart recorder is the only common
 * instrument whose paper already draws that difference. A flat trace means the
 * instrument was watching and nothing moved. Blank paper means it was not
 * watching. Every KPI tile ever drawn renders both as 0.
 *
 * That is not an ornament laid over the data. It decides the composition:
 *
 *   - The three channels share one time base but not one span, so the
 *     electricity channel runs to 2030 while the count channel stops at
 *     2026-06, and the paper past that point is blank rather than flat.
 *   - Facilities with no allocated power figure are drawn as an unruled block,
 *     not as a bar of length zero.
 *   - The years before the tagging convention caught on sit under a hatch that
 *     says the readings there are too low, rather than being cropped away.
 *
 * Everything on this page is read at build time from the committed observatory
 * payloads. There is no client-side fetch, no map engine and no charting
 * dependency; the only JavaScript that reaches the reader is the crosshair.
 */
import fs from "fs/promises";
import path from "path";

import Link from "next/link";

import {
  RecorderChart,
  type Channel,
} from "@/components/recorder/RecorderChart";
import { EventRow } from "@/components/recorder/EventRow";
import { PlotSheet } from "@/components/recorder/PlotSheet";
import {
  StackedTraces,
  type TraceRow,
} from "@/components/recorder/StackedTraces";
import { dropFlatRuns, monthIndex } from "@/lib/recorder";
import { getStageDistribution, listSites } from "@/lib/api";
import {
  getChanges,
  getNationalEnergy,
  getNationalSeries,
  getObservatoryMeta,
  getRegions,
  regionSlug,
  type Region,
} from "@/lib/observatory";

/** The paper the sheet is printed on runs from here to here. */
const CHART_FROM = "2014-01";
const CHART_TO = "2030-12";

/** Before this the tag was still being adopted, so every count reads too low. */
const DEAD_BAND_UNTIL = "2017-01";

const STACK_ROWS = 12;
const BAR_ROWS = 8;
const EVENT_ROWS = 7;

type Claim = "reported" | "observed" | "inferred" | "predicted";

const CLAIM_WORDS: Record<Claim, string> = {
  reported: "reported",
  observed: "observed",
  inferred: "inferred",
  predicted: "predicted",
};

/**
 * A rubber stamp, not a coloured pill.
 *
 * The word is always present and the colour only grades it, so the distinction
 * survives being printed, being read by someone who cannot separate the inks,
 * and being screenshotted into a slide.
 */
function Stamp({ claim }: { claim: Claim }) {
  return (
    <span className={`pp-stamp pp-stamp-${claim}`}>{CLAIM_WORDS[claim]}</span>
  );
}

async function readSeries(regionId: string) {
  try {
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "data", "series", `${regionId}.json`),
      "utf-8",
    );
    return JSON.parse(raw) as { points: { period: string; count: number }[] };
  } catch {
    return null;
  }
}

/** The Arizona study, or null when its payloads are absent from this build. */
async function loadArizona() {
  try {
    const [sites, stages] = await Promise.all([
      listSites({ limit: 1, sort: "-confidence" }),
      getStageDistribution(),
    ]);
    return {
      siteCount: stages.total_sites,
      topCode: sites.items[0]?.project_code ?? null,
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

  // The grid layer is built by a stage that can fail without taking the rest of
  // the poll with it, so this page has to read correctly before it has ever run
  // — the same guard /observatory-map already carries. Summing the two counts
  // straight into the sentence printed "0 substations and power plants", which
  // is not a fact this dataset is short of but a claim about the United States.
  const gridAssets = (meta.substation_count ?? 0) + (meta.plant_count ?? 0);
  const points = series?.points ?? [];
  const lastAdvance = points[points.length - 1]?.period ?? "2026-06";

  const historical = energy.filter((p) => p.series_kind === "historical");
  const projections = energy.filter((p) => p.series_kind === "projection");
  const latestPower = [...historical]
    .filter((p) => p.electricity_twh !== null)
    .sort((a, b) => b.year - a.year)[0];

  // Mid-year, because an annual total belongs at the middle of the year it
  // measures rather than at its first day.
  const atYear = (year: number) => monthIndex(`${year}-07`);

  const scenarioAt = (year: number, scenario: string) =>
    projections.find((p) => p.year === year && p.scenario === scenario)
      ?.electricity_twh ?? null;

  const projectionYears = [...new Set(projections.map((p) => p.year))].sort(
    (a, b) => a - b,
  );

  // Only the years that carry both edges. Defaulting a missing scenario to zero
  // drew a value nobody published, in the same ink as the ones LBNL did: the fan
  // would collapse to the axis at that year and open again after it, which reads
  // as a forecast of nothing rather than as an absent forecast. The reference
  // line below has always dropped its nulls rather than zeroing them.
  const bandYears = projectionYears.filter(
    (year) =>
      scenarioAt(year, "low") !== null && scenarioAt(year, "high") !== null,
  );

  // The fan opens from the last measured year, which is where LBNL opens it.
  const band = latestPower
    ? [
        {
          t: atYear(latestPower.year),
          lo: latestPower.electricity_twh!,
          hi: latestPower.electricity_twh!,
        },
        ...bandYears.map((year) => ({
          t: atYear(year),
          lo: scenarioAt(year, "low")!,
          hi: scenarioAt(year, "high")!,
        })),
      ]
    : [];

  const reference = latestPower
    ? [
        { t: atYear(latestPower.year), v: latestPower.electricity_twh! },
        ...projectionYears
          .map((year) => ({
            t: atYear(year),
            v: scenarioAt(year, "reference"),
          }))
          .filter((p): p is { t: number; v: number } => p.v !== null),
      ]
    : [];

  const channels: Channel[] = [
    {
      id: "count",
      name: "Facilities on the map",
      unit: "elements",
      pen: 1,
      claim: "observed",
      height: 214,
      max: 1800,
      render: "step",
      points: dropFlatRuns(
        points.map((p) => ({ t: monthIndex(p.period), v: p.count })),
        (p) => p.v,
      ),
      absentLabel: "no paper",
    },
    {
      id: "change",
      name: "Added that month",
      unit: "net",
      pen: 2,
      claim: "observed",
      height: 94,
      max: 150,
      render: "spike",
      points: points.map((p) => ({ t: monthIndex(p.period), v: p.change })),
      absentLabel: "no paper",
    },
    {
      id: "power",
      name: "US data-centre electricity",
      unit: "TWh",
      pen: 3,
      claim: "reported",
      height: 170,
      max: 900,
      render: "spot",
      points: historical
        .filter((p) => p.electricity_twh !== null)
        .map((p) => ({ t: atYear(p.year), v: p.electricity_twh! })),
      band,
      projection: reference,
      absentLabel: "not published",
    },
  ];

  // The stack: the densest counties, every one drawn at the ceiling below.
  const topCounties = [...counties]
    .sort((a, b) => b.facility_count - a.facility_count)
    .slice(0, STACK_ROWS);

  const stackRows: TraceRow[] = (
    await Promise.all(
      topCounties.map(async (county): Promise<TraceRow | null> => {
        const regionSeries = await readSeries(regionSlug(county.region_id));
        if (!regionSeries) return null;
        return {
          id: county.region_id,
          name: county.name,
          state: county.state,
          href: `/regions/${regionSlug(county.region_id)}`,
          value: `${county.facility_count.toLocaleString()} mapped`,
          points: dropFlatRuns(regionSeries.points, (p) => p.count),
        };
      }),
    )
  ).filter((row): row is TraceRow => row !== null);

  const stackCeiling = Math.max(...topCounties.map((c) => c.facility_count), 1);

  // The wall starts where its earliest county does. Sharing the main sheet's
  // 2014 origin left a fifth of every row blank before any trace could begin,
  // which reads as dead paper rather than as an absence of facilities.
  const stackFrom = stackRows.reduce((earliest, row) => {
    const first = row.points[0]?.period;
    return first && first < earliest ? first : earliest;
  }, lastAdvance);

  // The allocation. Bars for the counties that carry a figure; the facilities
  // that carry none are counted separately and never drawn as a short bar.
  const topByPower = [...counties]
    .sort((a, b) => b.est_mw - a.est_mw)
    .slice(0, BAR_ROWS);
  const powerCeiling = Math.max(...topByPower.map((c) => c.est_mw), 1);
  const noFigure =
    meta.facility_count - (meta.building_count ?? meta.facility_count);

  const netYear = points.slice(-12).reduce((sum, p) => sum + p.change, 0);
  const creations = changes.filter((c) => c.kind === "creation").length;
  const removals = changes.length - creations;

  // Stated rather than quietly cropped: the trace and the snapshot disagree,
  // and the difference is a real property of the history window.
  const traceEnd = points[points.length - 1]?.count ?? 0;
  const offTrace = meta.facility_count - traceEnd;

  return (
    <div className="recorder">
      <header className="pp-headband">
        <div>
          <h1 className="pp-plate-title">
            The United States data centre record
          </h1>
          <p className="pp-lede">
            {meta.facility_count.toLocaleString()} facilities at real
            coordinates, counted from public records. Three pens on one sheet:
            what was reported, what was inferred from it, and what is only
            projected — with the paper left blank wherever the instrument could
            not see.
          </p>
        </div>
        <dl className="pp-param-strip">
          <div>
            <dt>Station</dt>
            <dd>United States</dd>
          </div>
          <div>
            <dt>Chart speed</dt>
            <dd>1 yr / div</dd>
          </div>
          <div>
            <dt>Last advance</dt>
            <dd>{meta.last_polled}</dd>
          </div>
          <div>
            <dt>Regions</dt>
            <dd>
              {counties.length} · {states.length}
            </dd>
          </div>
        </dl>
      </header>

      <RecorderChart
        channels={channels}
        deadBandUntil={DEAD_BAND_UNTIL}
        lastAdvance={lastAdvance}
        fromPeriod={CHART_FROM}
        toPeriod={CHART_TO}
        restAt={lastAdvance}
      >
        <div className="pp-pens">
          <div className="pp-pen pp-pen-1">
            <span className="pp-pen-nib" />
            <span>
              <span className="pp-pen-name">Facilities on the map</span>
              <span className="pp-pen-meta">running total</span>
              <span className="pp-pen-meta">observed</span>
            </span>
          </div>
          <div className="pp-pen pp-pen-2">
            <span className="pp-pen-nib" />
            <span>
              <span className="pp-pen-name">Added that month</span>
              <span className="pp-pen-meta">net of removals</span>
              <span className="pp-pen-meta">observed</span>
            </span>
          </div>
          <div className="pp-pen pp-pen-3">
            <span className="pp-pen-nib" />
            <span>
              <span className="pp-pen-name">US electricity, TWh</span>
              <span className="pp-pen-meta">LBNL, mid-year</span>
              <span className="pp-pen-meta">reported, then predicted</span>
            </span>
          </div>
        </div>
      </RecorderChart>

      {/* ------------------------------------------------- what the pens mean */}
      <section className="pp-sheet-wide">
        <div className="pp-wide-head">
          <div>
            <h2 className="pp-sheet-title">Three kinds of number</h2>
            <p className="pp-note">
              They are not interchangeable, and this is the only page that has
              to explain it before you read anything else.
            </p>
          </div>
          <div className="pp-actions" style={{ marginTop: 0 }}>
            <Link className="pp-button pp-button-primary" href="/understand">
              What each of these means
            </Link>
            <Link className="pp-button" href="/methodology">
              How it is measured
            </Link>
          </div>
        </div>
        <div className="pp-wide-body">
          <p className="pp-note pp-measure" style={{ marginTop: 0 }}>
            A location is <Stamp claim="reported" /> — a contributor mapped it
            and you can open the element and check. A date is{" "}
            <Stamp claim="observed" />: the month OpenStreetMap first recorded
            the facility, never the month it was built, because OpenStreetMap
            carries no construction dates. A megawatt figure is{" "}
            <Stamp claim="inferred" />, a share of a national total published by
            Lawrence Berkeley National Laboratory divided up by building floor
            area, and it is an upper bound rather than a meter reading. Anything
            past {latestPower?.year ?? "the last measured year"} is{" "}
            <Stamp claim="predicted" /> — a published scenario, drawn as a range
            because that is how it was published.
          </p>
          <p className="pp-note pp-measure">
            <strong>The count and the curve disagree, deliberately.</strong> The
            trace ends at {traceEnd.toLocaleString()} while the snapshot holds{" "}
            {meta.facility_count.toLocaleString()}. The{" "}
            {offTrace.toLocaleString()} in between are facilities whose creation
            falls outside the recorded edit history, or arrived after the trace
            last advanced. They are in the count and not in the curve, and that
            is stated rather than reconciled away.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------------ the stack */}
      <section className="pp-sheet">
        <div className="pp-margin">
          <h2 className="pp-sheet-title">Where it concentrates</h2>
          <p className="pp-note">
            The densest {stackRows.length} counties, each drawn at the same
            gain. Scaling every row to its own maximum would make them all look
            equally busy; the finding is that they are not.
          </p>
          <dl className="pp-params">
            <div className="pp-param">
              <dt>Gain</dt>
              <dd>{stackCeiling} full scale</dd>
            </div>
            <div className="pp-param">
              <dt>Net, 12 mo</dt>
              <dd>
                {netYear >= 0 ? "+" : ""}
                {netYear.toLocaleString()}
              </dd>
            </div>
          </dl>
          <div className="pp-actions">
            <Link className="pp-button" href="/regions">
              All {regions.length} regions
            </Link>
          </div>
        </div>
        <div className="pp-plot pp-paper-field">
          <StackedTraces
            rows={stackRows}
            max={stackCeiling}
            fromPeriod={stackFrom}
            toPeriod={lastAdvance}
          />
        </div>
      </section>

      {/* ------------------------------------------------------- the allocation */}
      <section className="pp-sheet">
        <div className="pp-margin">
          <h2 className="pp-sheet-title">
            {noFigure.toLocaleString()} of them carry no power figure
          </h2>
          <p className="pp-note">
            A campus mapped as land, a bare point with no geometry, and a site
            still under construction are all counted and all located. None of
            them has a floor plate, so none of them takes a share of the
            national total. Their power is unknown, which is not a small number.
          </p>
        </div>
        <div className="pp-plot">
          <div className="pp-unruled">
            <span className="pp-label">No pen assigned</span>
            <span className="pp-unruled-count pp-num">
              {noFigure.toLocaleString()}
            </span>
            <span className="pp-note" style={{ margin: 0 }}>
              facilities on the sheet and off this scale
            </span>
          </div>

          <p className="pp-note">
            The other {(meta.building_count ?? 0).toLocaleString()} are
            buildings and do take a share. Every bar below ends at a stop mark,
            because each is an upper bound: the pieces re-sum to LBNL&apos;s
            published {meta.national_mw.toLocaleString()} MW for{" "}
            {meta.national_reference_year} exactly, and a test enforces it.{" "}
            <Stamp claim="inferred" />
          </p>

          <ul className="pp-bars">
            {topByPower.map((county: Region) => (
              <li className="pp-bar-row" key={county.region_id}>
                <span>
                  <Link href={`/regions/${regionSlug(county.region_id)}`}>
                    {county.name}
                  </Link>{" "}
                  <span className="pp-num" style={{ opacity: 0.6 }}>
                    {county.state}
                  </span>
                </span>
                <span className="pp-bar-track">
                  <span
                    className="pp-bar-fill"
                    style={{
                      width: `${(county.est_mw / powerCeiling) * 100}%`,
                    }}
                  />
                  <span
                    className="pp-bar-stop"
                    style={{
                      left: `calc(${(county.est_mw / powerCeiling) * 100}% - 1px)`,
                    }}
                  />
                </span>
                <span className="pp-bar-value">
                  {Math.round(county.est_mw).toLocaleString()} MW
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ----------------------------------------------------- the event marker */}
      <section className="pp-sheet">
        <div className="pp-margin">
          <h2 className="pp-sheet-title">What moved</h2>
          <p className="pp-note">
            The last {changes.length.toLocaleString()} edits: {creations}{" "}
            arrivals and {removals} removals.
          </p>
          <p className="pp-note">
            A removal means the element stopped matching the data-centre filter
            in OpenStreetMap. It is not a demolition and this site never says it
            is.
          </p>
          <div className="pp-actions">
            <Link className="pp-button" href="/changes">
              Full feed
            </Link>
          </div>
        </div>
        <div className="pp-plot">
          <ul className="pp-events">
            {changes.slice(0, EVENT_ROWS).map((change) => (
              <EventRow
                key={`${change.id}-${change.date}-${change.kind}`}
                change={change}
              />
            ))}
          </ul>
        </div>
      </section>

      {/* --------------------------------------------------------- the plot sheet */}
      <section className="pp-sheet-wide pp-sheet-map">
        <div className="pp-wide-head">
          <div>
            <h2 className="pp-sheet-title">The sheet itself</h2>
            <p className="pp-note">
              {gridAssets > 0 ? (
                <>
                  Every mapped facility, over the substations and power plants
                  they have to connect to — {gridAssets.toLocaleString()}{" "}
                  nationally.
                </>
              ) : (
                "Every mapped facility."
              )}{" "}
              The coastline under them is drawn in the paper&apos;s own hairline
              rather than in a pen, because it is the one thing on this sheet
              that was not measured: it is dissolved from the same county
              boundaries that decide which county each facility belongs to.
              Everything in ink is a record.
            </p>
            <p className="pp-note">
              The sheet covers the contiguous states, so it draws the contiguous
              share of that total rather than all of it. Alaska and Hawaii carry
              grid assets and no mapped data centres, so they are off it rather
              than empty on it; Puerto Rico&apos;s two facilities get an inset,
              and its grid, like theirs, stays off the paper. The figure the
              sheet itself is drawn from is in its description.
            </p>
          </div>
          <div>
            <div className="pp-pens pp-pens-row">
              <div className="pp-pen">
                <svg width="14" height="14" aria-hidden="true">
                  <circle cx="7" cy="7" r="4" className="pp-map-building" />
                </svg>
                <span>
                  <span className="pp-pen-name">Building</span>
                  <span className="pp-pen-meta">sized by floor plate</span>
                  <span className="pp-pen-meta">
                    takes a share of the total
                  </span>
                </span>
              </div>
              <div className="pp-pen">
                <svg width="14" height="14" aria-hidden="true">
                  <circle cx="7" cy="7" r="3.6" className="pp-map-nofigure" />
                </svg>
                <span>
                  <span className="pp-pen-name">
                    Campus, point or construction
                  </span>
                  <span className="pp-pen-meta">located and counted</span>
                  <span className="pp-pen-meta">no power figure at all</span>
                </span>
              </div>
            </div>
            <div className="pp-actions" style={{ marginTop: "0.9rem" }}>
              <Link className="pp-button" href="/observatory-map">
                Open the live map
              </Link>
            </div>
          </div>
        </div>
        <div className="pp-wide-body">
          <PlotSheet />
        </div>
      </section>

      {/* -------------------------------------------------------------- the index */}
      <section className="pp-sheet">
        <div className="pp-margin">
          <h2 className="pp-sheet-title">The rest of the roll</h2>
          <p className="pp-note">
            Each of these answers one question this sheet only summarises.
          </p>
          {arizona ? (
            <p className="pp-note">
              And a second, much deeper dataset: in one Arizona valley, Helios
              reads parcel transfers, permits and assessor records to argue
              where a data centre is <em>being built</em> — {arizona.siteCount}{" "}
              candidate sites, each with its evidence chain and its confidence
              scored in the open. <Stamp claim="inferred" />
            </p>
          ) : null}
        </div>
        <div className="pp-plot">
          <nav className="pp-index" aria-label="The rest of the site">
            {[
              {
                href: "/growth",
                name: "Growth over time",
                what: "The full series, every region, at daily, monthly and annual grain.",
              },
              {
                href: "/regions",
                name: "Regions",
                what: `All ${regions.length} counties and states holding at least one facility, sortable by count, floor area or allocated load.`,
              },
              {
                href: "/construction",
                name: "Mapped construction",
                what: `The ${meta.construction_count?.toLocaleString() ?? "—"} records contributors currently mark as being built — a forward signal, kept out of the operating estimates.`,
              },
              {
                href: "/large-load-filings",
                name: "Large-load filings",
                what: "Utility-regulator decisions that put an operator's own load figure on the public record. The only facility-scale power figures here that are reported rather than inferred.",
              },
              {
                href: "/observatory-map",
                name: "The national map",
                what: `All ${meta.facility_count.toLocaleString()} facilities, interactive, with the grid layer underneath.`,
              },
              {
                href: "/sources",
                name: "Sources",
                what: "Every declared source, including the ones Helios cannot reach and why. Gaps stay visible.",
              },
              {
                href: "/methodology",
                name: "Methodology and limitations",
                what: "The pipeline end to end, the allocation maths, and the list of things this dataset cannot see.",
              },
              ...(arizona
                ? [
                    {
                      href: "/sites",
                      name: "The Arizona site register",
                      what: `${arizona.siteCount} candidate sites inferred from parcel and permit records, each scored with its evidence attached.`,
                    },
                  ]
                : []),
            ].map((item) => (
              <Link className="pp-index-item" href={item.href} key={item.href}>
                <span className="pp-index-name">{item.name}</span>
                <span className="pp-index-what">{item.what}</span>
              </Link>
            ))}
          </nav>
        </div>
      </section>
    </div>
  );
}
