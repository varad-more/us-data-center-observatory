import Link from "next/link";

import { getObservatoryMeta } from "@/lib/observatory";

export const metadata = {
  title: "Methodology and limitations",
  description:
    "How the national observatory and the Arizona site model each produce their figures, and what neither can see.",
};

export default async function MethodologyPage() {
  const meta = await getObservatoryMeta();

  return (
    <div className="stack container-narrow">
      <h1>Methodology and limitations</h1>
      <p className="tagline">
        Helios publishes two datasets built by entirely different methods. The national
        observatory counts what has been mapped and divides up a reported national total.
        The Arizona study argues, from primary records, where a facility is probably being
        built. Neither method is used to support the other&apos;s claims. If you have not
        read <Link href="/understand">the basics</Link>, start there.
      </p>

      <h2>The national observatory</h2>

      <section className="card">
        <h3 className="card-title">Four stages, no database</h3>
        <p className="small">
          The whole pipeline runs from committed CSVs with no server and no database, so a
          contributor can rebuild every figure on the site from a clean checkout. One
          command, <code>make poll</code>, runs it end to end and prints what changed.
        </p>
        <ol className="small" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Snapshot.</strong> A tiled Overpass query pulls every US element
            tagged <code>telecom=data_center</code>, <code>building=data_center</code> or{" "}
            <code>industrial=data_centre</code>, with its geometry. Building outlines are
            converted to area on the WGS-84 ellipsoid, not by treating degrees as metres,
            and each element is reduced to a centroid, a footprint and its tags.
          </li>
          <li>
            <strong>History.</strong> The ohsome API replays OpenStreetMap&apos;s full
            edit history and reports the moment each element began — or stopped — matching
            that filter. This is the only defensible source for the time axis: an
            element&apos;s original creation date is when it was first drawn as{" "}
            <em>anything</em>, which is often years before it became a data centre.
          </li>
          <li>
            <strong>Placement.</strong> Each facility is matched to a US county by
            point-in-polygon against Census TIGER boundaries, indexed with an R-tree. The
            boundary vintage is recorded, because county codes do change.
          </li>
          <li>
            <strong>Allocation.</strong> LBNL&apos;s reported national electricity and
            water totals are divided across facilities in proportion to mapped building
            floor area, then summed into counties and states. Only facilities mapped as
            buildings take part: a campus mapped as a land parcel and a site mapped as
            under construction are counted and measured, but receive no share.
          </li>
        </ol>
        <p className="small" style={{ marginBottom: 0 }}>
          Re-running the pipeline with no upstream change produces no diff at all. The
          CSVs are written deterministically — stable sort, fixed precision — so that{" "}
          <code>git diff</code> between two polls is itself an honest change log.
        </p>
      </section>

      <section className="card">
        <h3 className="card-title">The power and water model, and its weakest link</h3>
        <p className="small">
          The allocation is conservative by construction: every facility receives its
          footprint&apos;s share of the national figure, so the state shares re-sum to the
          published total exactly. A test asserts this, because the property is the entire
          justification for the method.
        </p>
        <p className="small">
          What the model assumes is that power density per square metre is uniform across
          facilities. It is not. A dense multi-storey hall draws far more per square metre
          of ground than a single-storey shed, so tall sites are under-weighted and flat
          ones over-weighted.
        </p>
        <p className="small">
          <strong>What that weakest link turned out to be.</strong> This model used to
          allocate Virginia about 2,255 MW, against roughly 4,100 MW that Virginia&apos;s
          own legislative commission attributes to Northern Virginia alone — an under-read
          of about half in the densest region in the country. The cause was not the
          density assumption above. It was that &ldquo;footprint&rdquo; pooled three
          different things: a building&apos;s floor plate, the boundary of the land a
          campus sits on, and a site still under construction. Weighting by the pooled
          figure sent 82% of a measured national total to geometry that is not a building,
          and a single 3.1 km² parcel in Racine County, Wisconsin drew 598 MW while every
          mapped building in Loudoun County together drew 1,020 MW.
        </p>
        <p className="small" style={{ marginBottom: 0 }}>
          Weighting building floor area alone moves Loudoun County to 3,034 MW and Virginia
          to 4,972 MW, which is consistent with that independent figure where the old
          result was not. The correction cuts both ways and is not a claim of accuracy: the
          discarded parcels are real facilities whose load is now attributed to buildings
          elsewhere, so regions mapped campus-first are understated, and each such region
          says so on its own page. The density assumption above is unaffected and remains.
        </p>
      </section>

      <section className="card">
        <h3 className="card-title">What the observatory cannot see</h3>
        <ul className="small" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Construction dates.</strong> Not one facility in the dataset carries
            one, because OpenStreetMap does not record them. Every date here describes an
            edit to the map.
          </li>
          <li>
            <strong>Coverage.</strong> No authoritative public count of US data centres
            exists, so how much of reality these{" "}
            {meta.facility_count.toLocaleString()} represent is unknown, not merely
            unstated.
          </li>
          <li>
            <strong>Pre-2017 history.</strong> The tagging convention was barely used
            before then. That stretch of the curve is drawn hatched because it describes
            the tag, not the country.
          </li>
          <li>
            <strong>Whether a removal was a demolition.</strong> An element leaves the
            dataset when it stops matching the filter, which a retag does as readily as a
            teardown.
          </li>
          <li>
            <strong>203 facilities&apos; arrival.</strong> They were mapped before the
            retained history begins, so they appear in the counts but in no curve. Each
            region page states its own gap rather than hiding it.
          </li>
        </ul>
      </section>

      <h2>The Arizona site model</h2>

      <section className="card">
        <h3 className="card-title">How Helios reaches a conclusion</h3>
        <p className="small">
          Data flows in one direction, and every step is reversible for audit:
        </p>
        <ol className="small muted" style={{ paddingLeft: "1.2rem" }}>
          <li>
            A connector fetches bytes from a declared public source. The payload is hashed
            with SHA-256 and stored under a key derived from that hash, so a key cannot be
            reused for different content and re-fetching identical bytes is a no-op.
          </li>
          <li>
            A parser reads structured records out of the payload without interpreting them.
          </li>
          <li>
            A normalizer maps source-native fields onto Helios concepts, converts units,
            and applies the privacy policy. Each distinct assertion becomes its own
            evidence record with its own date.
          </li>
          <li>
            Parcels are clustered into sites by spatial adjacency <em>and</em> shared
            ownership. Either signal alone produces bad clusters.
          </li>
          <li>
            A weighted rule set scores each site, and every point of the score is recorded
            as a separate explanation row pointing at one evidence record.
          </li>
        </ol>
      </section>

      <section className="card">
        <h3 className="card-title">The confidence model</h3>
        <p className="small muted">
          Each evidence record maps to at most one rule and contributes{" "}
          <code>base weight &times; extraction confidence &times; recency</code>. The sum
          is squashed into 0&ndash;100 by a saturating function so that accumulating weak
          signals cannot imitate a strong one.
        </p>
        <p className="small muted">Three mechanisms deliberately hold scores down:</p>
        <ul className="small muted" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Diversity capping.</strong> A site supported by one kind of evidence
            cannot exceed 45% however much of it exists. Ten permits from one office are
            one fact observed ten times.
          </li>
          <li>
            <strong>Saturation.</strong> Contributions have diminishing returns.
          </li>
          <li>
            <strong>Staleness.</strong> Event evidence that stops progressing decays and
            eventually scores negative. Standing conditions &mdash; statements about the
            present, such as the county&rsquo;s current use classification &mdash; are
            exempt, because a facility does not become less likely to exist as its purchase
            deed ages.
          </li>
        </ul>
        <p className="small muted">
          Weights are domain-reasoned starting points taken from the project specification.
          They are <strong>not fitted to outcomes</strong>, and calibration is deliberately
          deferred until a historical backtest exists to calibrate against. Tuning weights
          now would produce numbers that look authoritative and mean nothing.
        </p>
      </section>

      <section className="card">
        <h3 className="card-title">Privacy</h3>
        <p className="small muted">
          County assessor records name private homeowners. Helios classifies every owner
          name during ingestion and suppresses those identified as natural persons or as
          trusts bearing an individual&rsquo;s name &mdash; <em>before</em> anything is
          written to the database, not as a display filter. No organization record is
          created for a private individual, because storing a redacted placeholder would
          still disclose that a person owns a particular parcel.
        </p>
        <p className="small muted">
          The classifier is biased toward redaction: an unclassifiable name is treated as
          personal. A company wrongly redacted costs a little recall; a homeowner wrongly
          published is a serious harm. The connector also declines to request owner mailing
          street addresses at all, so that data never reaches Helios.
        </p>
      </section>

      <section className="card">
        <h3 className="card-title">Known limitations of the site model</h3>
        <ul className="small muted" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Early-stage coverage is still uneven.</strong> ACC eDocket
            transmission and substation filings are parsed from recorded fixtures only
            &mdash; Helios does not scrape the live ASP.NET search. Municipal planning
            agenda PDFs are not yet automated. Mesa commercial building permits and EPA
            air facilities improve construction and generator recall, but coverage can
            still concentrate at Stage 7 when the assessor&rsquo;s DATA CENTERS label is
            the dominant signal.
          </li>
          <li>
            <strong>Ownership history is truncated.</strong> The assessor exposes only the
            most recent deed per parcel, so Helios observes a single transfer rather than a
            chain. Multi-year land assembly by successive entities is invisible.
          </li>
          <li>
            <strong>Score semantics are conflated.</strong> One number currently blends
            &ldquo;is this a data centre?&rdquo; with &ldquo;how far along is it?&rdquo;. A
            county-confirmed operating facility scores moderately rather than highly,
            because the model was designed for detecting emerging projects. Separating the
            two is a calibration task for the backtesting phase.
          </li>
          <li>
            <strong>Transmission-line distances are approximate.</strong> The Overpass
            query returns a centroid per circuit rather than a polyline, so distances are
            measured to a midpoint and treated as an upper bound.
          </li>
          <li>
            <strong>OpenStreetMap coverage is contributor-dependent.</strong> The absence
            of a substation in OSM is not evidence that none exists, and Helios draws no
            negative inference from it.
          </li>
          <li>
            <strong>No satellite analysis.</strong> No imagery credentials are configured,
            so no satellite observations exist. Nothing in the interface derives from
            remote sensing.
          </li>
          <li>
            <strong>No historical backtest yet.</strong> Until the replay harness runs,
            Helios has published no measured precision, recall, or lead time, and none
            should be inferred from the confidence figures.
          </li>
        </ul>
      </section>

      <section className="card">
        <h3 className="card-title">What Helios will not do</h3>
        <ul className="small muted" style={{ paddingLeft: "1.2rem" }}>
          <li>
            Name an operator without a direct filing. Circumstantial strength &mdash; a
            single-purpose LLC, an out-of-state mailing address, a nearby substation
            &mdash; never promotes to an attribution.
          </li>
          <li>Bypass authentication, CAPTCHAs, or any technical access control.</li>
          <li>Publish exact water or power consumption without a reported figure.</li>
          <li>Present scenario output as measurement.</li>
        </ul>
      </section>
    </div>
  );
}
