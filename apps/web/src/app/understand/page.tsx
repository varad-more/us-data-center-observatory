/**
 * The background a reader needs before any figure on this site means anything.
 *
 * Helios published counts, megawatts and gallons for months without ever saying
 * what a data centre contains, why power rather than floor area is the unit the
 * industry actually trades in, or why cooling spends water at all. A reader who
 * does not already work in the field could read every page and still not know
 * whether 1,020 MW in one county is a lot.
 *
 * Every quantitative claim here is either derived live from the committed data
 * or attributed to the source it came from. Where a comparison is an
 * illustration rather than a measurement — "about this many homes" — the
 * arithmetic is shown so the reader can see exactly what assumption is doing
 * the work.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AssertionBadge } from "@/components/AssertionBadge";
import { getFacilities, getNationalEnergy, getObservatoryMeta } from "@/lib/observatory";

export const metadata: Metadata = {
  title: "Understanding data centres",
  description:
    "What a data centre contains, why electricity decides where one gets built, why cooling spends water, and how to read every figure Helios publishes.",
};

/**
 * Average annual electricity use of a US household, in kWh.
 *
 * Used only to give a megawatt a human scale, and the division is shown on the
 * page rather than hidden here. Rounded from the EIA's residential average,
 * which has sat near this level for a decade.
 */
const HOUSEHOLD_KWH_PER_YEAR = 10_500;

const HOURS_PER_YEAR = 8760;

export default async function UnderstandPage() {
  const [meta, energy, facilities] = await Promise.all([
    getObservatoryMeta(),
    getNationalEnergy(),
    getFacilities(),
  ]);

  const latestPower = energy
    .filter((p) => p.series_kind === "historical" && p.electricity_twh !== null)
    .sort((a, b) => b.year - a.year)[0];
  const latestWater = energy
    .filter((p) => p.series_kind === "historical" && p.water_bgal !== null)
    .sort((a, b) => b.year - a.year)[0];
  const outlook = energy.find(
    (p) => p.series_kind === "projection" && p.year === 2030 && p.scenario === "reference",
  );

  // Measured from the committed dataset rather than asserted, because the
  // spread is the argument for footprint-weighting and a stale number would
  // quietly undermine it.
  //
  // Buildings only. Including the campus land parcels compared a median floor
  // plate against a 3.2 km2 property boundary and reported the ratio as a spread
  // between buildings, which is the very conflation this page warns about.
  const areas = facilities.features
    .filter((f) => f.properties.site_class === "building")
    .map((f) => f.properties.footprint_m2)
    .filter((a) => a > 0)
    .sort((a, b) => a - b);
  const medianArea = areas[Math.floor(areas.length / 2)] ?? 0;
  const largestArea = areas[areas.length - 1] ?? 0;
  const spread = medianArea > 0 ? Math.round(largestArea / medianArea) : 0;

  // The largest land parcel, for contrast with the largest building. Derived
  // for the same reason as the rest: a typed figure here drifted once already.
  const largestParcel = Math.max(
    0,
    ...facilities.features
      .filter((f) => f.properties.site_class === "site")
      .map((f) => f.properties.footprint_m2),
  );
  const parcelRatio = medianArea > 0 ? Math.round(largestParcel / medianArea) : 0;

  // A household's *average* draw: annual energy spread over the year. This is
  // the only honest way to compare a continuous megawatt to a home, and it is
  // why the comparison is about averages and not about peak demand.
  const householdKw = HOUSEHOLD_KWH_PER_YEAR / HOURS_PER_YEAR;
  const homesPerMw = Math.round(1000 / householdKw);

  return (
    <div className="stack container-narrow">
      <div>
        <p className="eyebrow">Background</p>
        <h1>Understanding data centres</h1>
        <p className="tagline">
          Enough of the physical and economic picture to read the rest of this site
          properly: what these buildings contain, why their size is quoted in megawatts
          rather than square feet, why cooling them spends water, and what each number
          here is and is not claiming.
        </p>
      </div>

      <section className="card">
        <h2 className="card-title">What is actually inside one</h2>
        <p className="small">
          A data centre is a building whose purpose is to keep computers running without
          interruption. Strip away the scale and it is three systems wrapped around each
          other:
        </p>
        <dl className="kv small">
          <dt>The white space</dt>
          <dd>
            Rows of racks — steel frames, each holding servers, storage and networking
            gear. This is the part doing the work, and its electricity use is called the{" "}
            <strong>IT load</strong>.
          </dd>
          <dt>Power</dt>
          <dd>
            A connection to the transmission grid, transformers to step it down,
            uninterruptible power supplies with batteries to bridge the seconds before
            backup generators start, and usually diesel generators to carry the site
            through an outage. Redundancy is the product being sold.
          </dd>
          <dt>Cooling</dt>
          <dd>
            Almost every watt a server draws leaves as heat, and the heat has to go
            somewhere or the equipment fails. Chillers, air handlers, and often cooling
            towers move it outdoors. This is the second-largest consumer of electricity in
            the building and the reason water enters the story at all.
          </dd>
        </dl>
        <p className="small" style={{ marginBottom: 0 }}>
          What varies enormously is scale. Across the {areas.length.toLocaleString()}{" "}
          mapped buildings in this dataset with an outline drawn, the median covers{" "}
          {medianArea.toLocaleString()} m² while the largest covers{" "}
          {largestArea.toLocaleString()} m² — a spread of roughly{" "}
          <strong>{spread.toLocaleString()} to one</strong>. That gap is the reason Helios
          weights its power allocation by building floor area instead of dividing the
          national total evenly across facilities; a flat per-facility figure would be
          wrong by about an order of magnitude at both ends of that range.
        </p>
        <p className="small" style={{ marginBottom: 0 }}>
          Those are <em>buildings</em>. The same OpenStreetMap tags are also used for the
          land a campus sits on, and the largest such parcel covers{" "}
          {(largestParcel / 1e6).toFixed(1)} km² — {parcelRatio.toLocaleString()} times the
          median building. Counting that area as though it were floor space is what
          the allocation used to do, and it sent 82% of the national total to geometry
          that is not a building. Helios now weights buildings only, and says so wherever
          a region has parcels it therefore cannot estimate.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">Why the unit is the megawatt</h2>
        <p className="small">
          Ask how big a data centre is and the answer comes back in megawatts, not floor
          area. That is not jargon — it reflects what is actually scarce. Floor space is
          straightforward to build. A grid connection able to deliver hundreds of
          megawatts continuously is not, and in several regions the waiting list to get
          one now runs for years. Power is the binding constraint, so power is the unit of
          account.
        </p>
        <p className="small">
          The distinction that trips people up is <strong>power versus energy</strong>. A
          megawatt (MW) is a rate — how fast electricity is being used at this instant.
          A megawatt-hour (MWh) is a quantity — a megawatt sustained for an hour. A
          terawatt-hour (TWh) is a million of those.
        </p>
        <div className="notice">
          <strong>Worked example, using the figures on this site.</strong> LBNL reports
          that US data centres used{" "}
          {latestPower?.electricity_twh?.toLocaleString()} TWh in {latestPower?.year}.
          Spread evenly across the {HOURS_PER_YEAR.toLocaleString()} hours in a year, that
          is a continuous draw of about{" "}
          <strong>{meta.national_mw.toLocaleString()} MW</strong> — the figure Helios
          allocates across counties. Data centres run flat out around the clock, so
          unusually for an electrical load, the average and the peak are close together.
        </div>
        <p className="small" style={{ marginBottom: 0 }}>
          For a human sense of scale: an average US home uses roughly{" "}
          {HOUSEHOLD_KWH_PER_YEAR.toLocaleString()} kWh a year, which spread over{" "}
          {HOURS_PER_YEAR.toLocaleString()} hours is a continuous{" "}
          {householdKw.toFixed(2)} kW. One megawatt is therefore about{" "}
          <strong>{homesPerMw.toLocaleString()} homes</strong> worth of average
          electricity demand. A single large campus drawing 300 MW is in the range of a
          small city. Treat this as an illustration, not a measurement: it compares
          averages, and a neighbourhood&apos;s peak demand behaves quite differently from
          a data centre&apos;s flat one.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">PUE, and why the building uses more than the computers</h2>
        <p className="small">
          The industry&apos;s standard efficiency measure is <strong>PUE</strong>, power
          usage effectiveness: total facility electricity divided by the IT load alone.
        </p>
        <div className="snippet">PUE = total facility energy ÷ IT equipment energy</div>
        <p className="small" style={{ marginTop: "0.75rem" }}>
          A PUE of 1.0 is the unreachable floor — every watt reaching the computers and
          nothing spent on cooling, conversion losses or lighting. A PUE of 1.5 means that
          for every kilowatt of computing, another half-kilowatt goes to running the
          building. The gap between an efficient hyperscale facility and an older
          enterprise room is large, and it is mostly cooling.
        </p>
        <p className="small" style={{ marginBottom: 0 }}>
          Two cautions worth carrying. PUE is almost always self-reported and rarely
          audited. And it is a <em>ratio</em>, so it improves when the computers work
          harder — a site can report a better PUE while consuming considerably more
          electricity in absolute terms. Nothing on this site is derived from a PUE
          figure; it is described here because you will meet it everywhere else.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">Why cooling spends water</h2>
        <p className="small">
          The cheapest way to reject a large amount of heat is to evaporate water. A
          cooling tower does exactly that: warm water is trickled through moving air, some
          of it evaporates, and the evaporation carries the heat away. The water that
          evaporates is consumed — it does not return to the source.
        </p>
        <p className="small">
          The alternative, a closed-loop or air-cooled design, consumes almost no water,
          but rejecting the same heat without evaporation takes noticeably more
          electricity. So the industry faces a direct trade: <strong>water or
          power</strong>. Which is chosen depends on climate, local water price and
          politics — which is why the same operator builds differently in Oregon and in
          Arizona. The efficiency measure here is <strong>WUE</strong>, water usage
          effectiveness, in litres per kilowatt-hour of IT load.
        </p>
        <p className="small" style={{ marginBottom: 0 }}>
          LBNL puts direct water consumption by US data centres at{" "}
          <strong>{latestWater?.water_bgal} billion gallons</strong> in {latestWater?.year}
          . &ldquo;Direct&rdquo; matters: it counts water evaporated on site and excludes
          the water consumed generating the electricity in the first place, which is
          substantially larger and depends entirely on how the local grid is powered. The
          water figures on this site are the direct kind, because that is what the source
          reports.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">Why they cluster so tightly</h2>
        <p className="small">
          One county in this dataset holds more mapped data centres than most states. That
          is not an artefact of the data; the industry genuinely concentrates, for
          reasons that compound:
        </p>
        <ul className="small" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Fibre follows fibre.</strong> Long-haul routes and internet exchanges
            were laid where earlier ones already ran. Northern Virginia&apos;s density
            traces back to the region hosting one of the internet&apos;s earliest major
            exchange points; networks converged there, and networks are what a data centre
            is selling access to.
          </li>
          <li>
            <strong>Power availability and price.</strong> Substation capacity and cheap
            generation attract siting more than almost anything else, which is why the map
            lights up along particular transmission corridors.
          </li>
          <li>
            <strong>Tax treatment.</strong> Many states exempt data-centre equipment from
            sales tax. On a build where the servers cost more than the building, that
            changes the arithmetic decisively.
          </li>
          <li>
            <strong>Latency to users.</strong> Distance costs milliseconds, so anything
            serving interactive traffic wants to be near population.
          </li>
          <li>
            <strong>Everyone else being there.</strong> Once a cluster exists, it has the
            trained electricians, the permitting precedent, the peering partners and the
            supply chain. Each new build makes the next one easier.
          </li>
        </ul>
        <p className="small" style={{ marginBottom: 0 }}>
          The consequence for reading this site: national totals hide almost everything
          interesting. The <Link href="/regions">regions view</Link> is where the
          concentration becomes visible.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">How to read every number here</h2>
        <p className="small">
          Helios keeps three kinds of claim strictly apart, and labels which is which
          wherever a figure appears.
        </p>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Claim</th>
                <th>Class</th>
                <th>What it rests on</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>This facility is at this coordinate</td>
                <td>
                  <AssertionBadge assertion="reported" />
                </td>
                <td>An OpenStreetMap contributor mapped it and tagged it.</td>
              </tr>
              <tr>
                <td>It first appeared on the map in this month</td>
                <td>
                  <span className="pill">observed</span>
                </td>
                <td>
                  OpenStreetMap&apos;s edit history records when the element began
                  matching the data-centre filter.
                </td>
              </tr>
              <tr>
                <td>It was built in that month</td>
                <td>
                  <span className="pill pill-negative">never claimed</span>
                </td>
                <td>
                  OpenStreetMap carries no construction dates. Not one facility in this
                  dataset has one.
                </td>
              </tr>
              <tr>
                <td>US data centres used {latestPower?.electricity_twh} TWh</td>
                <td>
                  <AssertionBadge assertion="reported" />
                </td>
                <td>Published by Lawrence Berkeley National Laboratory.</td>
              </tr>
              <tr>
                <td>This county accounts for N megawatts</td>
                <td>
                  <AssertionBadge assertion="inferred" />
                </td>
                <td>
                  Its mapped footprint&apos;s share of that national total. Not a meter
                  reading, and an upper bound.
                </td>
              </tr>
              <tr>
                <td>
                  {outlook?.year} will reach {outlook?.electricity_twh} TWh
                </td>
                <td>
                  <AssertionBadge assertion="predicted" />
                </td>
                <td>A published scenario, quoted with its range, not a forecast Helios makes.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="small" style={{ marginBottom: 0 }}>
          Why the megawatt figures are <em>upper bounds</em>: the national total is spread
          across only the facilities that have been mapped. Every real data centre nobody
          has mapped has its consumption silently handed to the ones that have been. The
          allocation is exact by construction — the state shares re-sum to{" "}
          {meta.national_mw.toLocaleString()} MW — but exact arithmetic on an incomplete
          denominator is still an over-estimate per facility.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">What this site cannot tell you</h2>
        <ul className="small" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Whether a region truly has no data centres.</strong> A county showing
            zero has not been shown to have none — it may simply have no one mapping it.
            OpenStreetMap coverage is contributor-driven and uneven.
          </li>
          <li>
            <strong>How complete the {meta.facility_count.toLocaleString()} is.</strong>{" "}
            No authoritative public count of US data centres exists to check it against,
            so the coverage rate is genuinely unknown rather than merely unstated.
          </li>
          <li>
            <strong>When anything was built.</strong> The growth curve is a record of
            mapping activity. Its near-zero start before 2017 is a tagging convention
            being adopted, not an empty country, which is why that stretch is drawn
            hatched rather than cropped away.
          </li>
          <li>
            <strong>That a removal means a demolition.</strong> An element leaves this
            dataset when it stops matching the filter — which happens when a contributor
            retags it just as readily as when a building comes down.
          </li>
          <li>
            <strong>What any individual facility actually draws.</strong> Per-site metered
            power and water are not public. Everything here is an allocated share.
          </li>
        </ul>
        <p className="small" style={{ marginBottom: 0 }}>
          The <Link href="/methodology">methodology page</Link> states how each figure is
          produced and lists the known defects in full.
        </p>
      </section>

      <section className="card">
        <h2 className="card-title">Glossary</h2>
        <dl className="kv small">
          <dt>Colocation</dt>
          <dd>
            A facility renting space, power and cooling to many customers who bring their
            own servers.
          </dd>
          <dt>Hyperscale</dt>
          <dd>
            A very large facility operated by a single company for its own cloud or
            platform — the buildings that dominate the footprint figures here.
          </dd>
          <dt>IT load</dt>
          <dd>Electricity drawn by the computing equipment itself, excluding the building.</dd>
          <dt>kW / MW / GW</dt>
          <dd>
            Units of power, each a thousand times the last. Rates, not amounts.
          </dd>
          <dt>MWh / TWh</dt>
          <dd>
            Units of energy: power sustained over time. 1 TWh is one million MWh.
          </dd>
          <dt>PUE</dt>
          <dd>Total facility energy ÷ IT energy. Lower is better; 1.0 is unreachable.</dd>
          <dt>WUE</dt>
          <dd>Litres of water consumed per kWh of IT energy.</dd>
          <dt>Footprint</dt>
          <dd>
            Ground area of the mapped building outline, in square metres, computed on the
            ellipsoid rather than from degrees.
          </dd>
          <dt>FIPS</dt>
          <dd>
            The federal numeric code identifying a US county — how facilities are matched
            to regions here.
          </dd>
          <dt>Interconnection queue</dt>
          <dd>
            The waiting list to connect a large new load or generator to the grid. Often
            the real schedule constraint on a project.
          </dd>
        </dl>
      </section>
    </div>
  );
}
