/**
 * Site footer.
 *
 * The "where the numbers come from" column is generated from the source registry
 * rather than typed by hand. Helios's registry already declares every source it
 * uses along with whether a connector actually exists, so a hand-written list
 * would be a second copy of that truth — free to drift, and drifting in the one
 * direction the project cannot afford: claiming a source that is not feeding
 * anything.
 *
 * Only sources with a working connector are listed as feeding the data. The
 * count of declared-but-not-ingesting sources is stated beside them, because the
 * registry exists to make gaps visible, not to hide them.
 */
import fs from "fs/promises";
import path from "path";

import Link from "next/link";

interface SourceItem {
  slug: string;
  name: string;
  base_url: string | null;
  jurisdiction: string | null;
  connector_status: string;
}

interface SourcesPayload {
  items: SourceItem[];
  coverage_summary: Record<string, number>;
}

interface ExportMeta {
  generated_at: string;
}

async function readJson<T>(...segments: string[]): Promise<T | null> {
  // Read from disk at build time; a static export has no server at runtime.
  try {
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "api", ...segments),
      "utf-8",
    );
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function formatDate(iso: string): string | null {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export async function SiteFooter() {
  const [sources, meta] = await Promise.all([
    readJson<SourcesPayload>("sources.json"),
    readJson<ExportMeta>("meta.json"),
  ]);

  const feeding = (sources?.items ?? []).filter(
    (item) => item.connector_status === "implemented",
  );
  const declaredOnly = (sources?.items ?? []).length - feeding.length;
  const exportedOn = meta ? formatDate(meta.generated_at) : null;

  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <div className="footer-grid">
          <div>
            <p className="footer-mark">Helios</p>
            <p className="footer-blurb">
              Where data centres are, how fast they are arriving, and what they cost in
              electricity and water. Counted nationally from OpenStreetMap, and in one
              Arizona valley inferred in depth from parcel and permit records. Every
              figure traces back to the document it came from.
            </p>
            {exportedOn && (
              <p className="freshness">
                <span className="dot" aria-hidden="true" />
                Snapshot exported {exportedOn}
              </p>
            )}
          </div>

          <nav className="footer-col" aria-label="Observatory">
            <h2>Observatory</h2>
            <ul>
              <li>
                <Link href="/">Overview</Link>
              </li>
              <li>
                <Link href="/growth">Growth over time</Link>
              </li>
              <li>
                <Link href="/regions">Regions</Link>
              </li>
              <li>
                <Link href="/construction">Mapped construction</Link>
              </li>
              <li>
                <Link href="/large-load-filings">Large-load filings</Link>
              </li>
              <li>
                <Link href="/observatory-map">US map</Link>
              </li>
              <li>
                <Link href="/changes">Changes</Link>
              </li>
            </ul>
          </nav>

          <nav className="footer-col" aria-label="Arizona study and reference">
            <h2>Study &amp; reference</h2>
            <ul>
              <li>
                <Link href="/sites">Arizona sites</Link>
              </li>
              <li>
                <Link href="/map">Arizona parcel map</Link>
              </li>
              <li>
                <Link href="/understand">Understanding data centres</Link>
              </li>
              <li>
                <Link href="/methodology">Methodology &amp; limitations</Link>
              </li>
              <li>
                <Link href="/sources">Data sources</Link>
              </li>
              <li>
                <a href="https://github.com/varad-more/us-data-center-observatory">Source on GitHub</a>
              </li>
            </ul>
          </nav>

          <div className="footer-col">
            <h2>Where the records come from</h2>
            <ul>
              {feeding.map((source) => (
                <li key={source.slug}>
                  {source.base_url ? (
                    <a href={source.base_url}>{source.name}</a>
                  ) : (
                    source.name
                  )}
                  {source.jurisdiction && <span>{source.jurisdiction}</span>}
                </li>
              ))}
            </ul>
            {declaredOnly > 0 && (
              <p className="footer-gap">
                <Link href="/sources">
                  {declaredOnly} further sources declared, not yet ingesting
                </Link>
              </p>
            )}
          </div>
        </div>

        <div className="footer-bar">
          <p>
            Helios infers development activity from public records. Confidence scores are
            model output, not fact. Helios does not assert the identity of any facility
            operator unless a direct filing establishes it.
          </p>
          <p>
            Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS. Data
            centre locations, footprints and edit history &copy; OpenStreetMap
            contributors, ODbL. National electricity and water totals from Lawrence
            Berkeley National Laboratory. County boundaries from the US Census
            Bureau. Owner names
            classified as belonging to private individuals are redacted before storage.{" "}
            <a href="https://github.com/varad-more/us-data-center-observatory/blob/main/LICENSE">
              Apache-2.0
            </a>
            .
          </p>
        </div>

        {/* Its own row rather than a third column in the bar above: the bar
            carries disclaimers about the data, and a byline folded in beside
            them reads as one more caveat instead of as authorship. */}
        <div className="footer-byline">
          <p>
            Built and maintained by{" "}
            <a href="https://varadmore.me" rel="author">
              Varad More
            </a>
            <span className="byline-contact">
              <a href="https://varadmore.me">varadmore.me</a> &middot;{" "}
              <a href="https://github.com/varad-more">github.com/varad-more</a>
            </span>
          </p>
          <p>
            <a href="https://github.com/varad-more/us-data-center-observatory">
              Read the source
            </a>{" "}
            &middot; <Link href="/methodology">How it is measured</Link> &middot;{" "}
            <Link href="/sources">What it is measured from</Link>
          </p>
        </div>
      </div>
    </footer>
  );
}
