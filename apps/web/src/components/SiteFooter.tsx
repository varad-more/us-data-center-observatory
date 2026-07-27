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
          <div className="footer-brand">
            <p className="footer-mark">Helios</p>
            <p className="footer-blurb">
              An evidence-first view of how data-centre projects move from land assembly
              through permitting, construction, and grid connection — assembled from
              public records, with every figure traceable to the document it came from.
            </p>
            {exportedOn && (
              <p className="freshness">
                <span className="dot" aria-hidden="true" />
                Snapshot exported {exportedOn}
              </p>
            )}
          </div>

          <nav className="footer-col" aria-label="Site">
            <h2>The site</h2>
            <ul>
              <li>
                <Link href="/">Observatory</Link>
              </li>
              <li>
                <Link href="/map">Map</Link>
              </li>
              <li>
                <Link href="/sites">Sites</Link>
              </li>
              <li>
                <Link href="/sources">Data sources</Link>
              </li>
              <li>
                <Link href="/methodology">Methodology &amp; limitations</Link>
              </li>
              <li>
                <a href="https://github.com/varad-more/project-helios">Source on GitHub</a>
              </li>
            </ul>
          </nav>

          <div className="footer-col footer-sources">
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
            Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS. Power
            infrastructure data &copy; OpenStreetMap contributors, ODbL. Owner names
            classified as belonging to private individuals are redacted before storage.{" "}
            <a href="https://github.com/varad-more/project-helios/blob/main/LICENSE">
              Apache-2.0
            </a>
            .
          </p>
        </div>
      </div>
    </footer>
  );
}
