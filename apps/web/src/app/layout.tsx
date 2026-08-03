import type { Metadata } from "next";
import localFont from "next/font/local";

import { DemoDataBanner } from "@/components/DemoDataBanner";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteNav } from "@/components/SiteNav";
import { THEME_INIT_SCRIPT } from "@/components/ThemeToggle";
import { StructuredData } from "@/components/StructuredData";
import { getNationalSeries, getObservatoryMeta } from "@/lib/observatory";
import { SITE_URL } from "@/lib/site";
import "./globals.css";
import "./recorder.css";

/**
 * The site's two faces.
 *
 * Archivo carries the margin plates: a grotesque drawn from the American gothics
 * that set newspaper decks and signage, with a width axis, which is what lets a
 * label plate compress to fit its column instead of wrapping or shipping a
 * second file. Azeret Mono carries every measured value — monospace here is
 * measurement notation, not a costume for "technical": these are readings off an
 * instrument, and they have to align in a column to be compared.
 *
 * Fraunces used to carry the display voice on the fourteen routes that were not
 * the front page. There are no such routes now, so it is not loaded: an unused
 * variable font is 70 KB the reader downloads to render nothing.
 */
const archivo = localFont({
  src: "./fonts/archivo-latin-var.woff2",
  variable: "--font-archivo",
  display: "swap",
  weight: "400 800",
});

const azeret = localFont({
  src: "./fonts/azeret-mono-latin-var.woff2",
  variable: "--font-azeret",
  display: "swap",
  weight: "300 700",
});

const DESCRIPTION =
  "Where US data centres are, how fast they are arriving, and what they draw in electricity and water — counted from public records.";

export const metadata: Metadata = {
  // Absolute origin for canonical and Open Graph URLs. Without it Next emits
  // relative og:url values, which are ignored, and every share of any page
  // resolves to whatever host pasted it.
  metadataBase: new URL(SITE_URL),
  title: {
    // The homepage is the one page whose title the template never touches, so it
    // has to carry its own search terms. It used to lead with the brand, which is
    // the one string nobody types - every other page now leads with "Data centres
    // in <place>". Kept under 60 characters so a result page shows all of it.
    default: "US data centres: where they are and what they draw | Helios",
    template: "%s | Helios",
  },
  description: DESCRIPTION,
  // A link to this site is most often pasted into a chat window, and without
  // these it unfurls as a bare URL. Neither block sets a title: a literal one
  // here wins over the page's own, which made every shared county page announce
  // itself as the site index. Omitting it lets the title template above resolve,
  // so a shared /regions/county-51107 unfurls as "Loudoun County | Helios".
  openGraph: {
    type: "website",
    siteName: "Helios US AI Infrastructure Observatory",
    description: DESCRIPTION,
    url: SITE_URL,
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    description: DESCRIPTION,
  },
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Read rather than hardcoded: a structured-data block that disagrees with the
  // page it sits on is the same claim published twice, differently.
  const [meta, series] = await Promise.all([
    getObservatoryMeta(),
    getNationalSeries(),
  ]);

  return (
    <html
      lang="en"
      className={`${archivo.variable} ${azeret.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Runs before first paint so a dark-mode reader never sees the ivory
            ground flash. Must be inline and blocking; see THEME_INIT_SCRIPT. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <StructuredData
          siteUrl={SITE_URL}
          facts={{
            facilityCount: meta.facility_count,
            lastPolled: meta.last_polled,
            seriesFrom: series?.points[0]?.period ?? null,
            seriesTo: series?.points[series.points.length - 1]?.period ?? null,
          }}
        />
      </head>
      <body>
        <div
          hidden
          dangerouslySetInnerHTML={{
            __html: `<!--
IMPECCABLE DIRECTION CONTRACT · seed 133091bd

THESIS: A flat trace and blank paper are different facts. This front page is a
strip-chart recorder because it is the only instrument whose paper already draws
that difference; it refuses the KPI-tile dashboard, which renders "measured, zero"
and "not measured" identically.

OWN-WORLD: Process-recorder chart paper (#dde3d6) ruled in printed rust, smoked
drum (#1a1815) in dark. Three validated pen inks, fixed order, never cycled.
Tractor-feed perforations down both edges. Archivo margin plates in tracked caps,
Azeret Mono for every reading. Stamps, not pills. Neatlines, not cards.

STORY: The visitor sees three channels on one time base, understands within
seconds that one is reported and one is projected, and learns that 347 facilities
carry no power figure at all — then goes to a region, the method, or the source.

FIRST VIEWPORT: A full-width header band carries the title, the lede and the
instrument parameter strip. Below it the sheet splits: margin plate with the pen
assignments and the crosshair readout on the left, three channels on the right,
the pre-2017 dead band hatched across all of them, and the "chart ends" rule
where the count's paper runs out. The chart itself is the invitation; the primary
action sits one scroll down under the claims sheet.

FORM: Chart Recorder, candidate 6 of the grounded list, seed key 133091bd.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, and DESIGN.md
-->`,
          }}
        />
        <div className="shell">
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          <SiteNav />

          <DemoDataBanner />

          <main id="main" className="container">
            {children}
          </main>

          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
