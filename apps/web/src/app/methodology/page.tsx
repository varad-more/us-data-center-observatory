export const metadata = { title: "Methodology and limitations" };

export default function MethodologyPage() {
  return (
    <div className="stack container-narrow">
      <h1>Methodology and limitations</h1>

      <section className="card">
        <h2 className="card-title">How Helios reaches a conclusion</h2>
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
        <h2 className="card-title">The confidence model</h2>
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
        <h2 className="card-title">Privacy</h2>
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
        <h2 className="card-title">Known limitations</h2>
        <ul className="small muted" style={{ paddingLeft: "1.2rem" }}>
          <li>
            <strong>Early-stage coverage is weak.</strong> The strongest early-warning
            signals &mdash; transmission filings, substation applications, planning
            applications &mdash; live in the Arizona Corporation Commission eDocket and
            municipal agenda PDFs, neither of which Helios can currently read
            automatically. Present coverage therefore concentrates at Stage 7, where the
            assessor&rsquo;s classification arrives <em>after</em> a facility exists. This
            is the single largest gap between what Helios does today and what it is for.
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
        <h2 className="card-title">What Helios will not do</h2>
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
