import type { Metadata } from "next";

/**
 * Where this deployment is published.
 *
 * Kept in one place because three unrelated things need the same absolute
 * origin — the sitemap, robots.txt, and the canonical/Open Graph URLs — and
 * three copies of a hostname is three chances to publish a link to somewhere
 * the site is not. The default matches `public/CNAME`, which is the file
 * GitHub Pages actually reads; a fork sets NEXT_PUBLIC_SITE_URL instead of
 * editing this.
 */
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://us-data-center-observatory.varadmore.me"
).replace(/\/$/, "");

/**
 * The Open Graph fields that are true of every page, in one object to spread.
 *
 * Next does not merge `openGraph` down the tree — a route that sets its own
 * replaces the parent's outright — so the region pages, which set a title and a
 * URL, were silently dropping the site name and the locale the root layout
 * declares. Spreading this is what keeps a shared county page unfurling like
 * the rest of the site instead of like a bare link.
 *
 * Nothing page-specific belongs here. A literal `description` or `url` in the
 * root layout does not fall back to the page's own; it overrides it, which is
 * why every route but the regions used to announce the front page's blurb and
 * the front page's URL. Those two are set per route or not at all. The card
 * image is page-specific in the same way — see OG_IMAGE.
 */
export const OG_BASE = {
  type: "website" as const,
  siteName: "Helios US AI Infrastructure Observatory",
  locale: "en_US",
};

/**
 * The share card, which the landing page carries and no other route does.
 *
 * Drawn by `scripts/build_og_image.py`. 1200x630 is the frame X crops
 * `summary_large_image` to and the size LinkedIn resamples from, so the card
 * travels to both uncropped.
 *
 * It is deliberately not in OG_BASE. One card that says "US data centres" is
 * the right picture for the front door and the wrong one for 324 county pages,
 * where it would put the same national headline above 324 different local
 * counts. Those pages already carry their own figures in the title and the
 * description, which is the part a reader reads; giving them all one shared
 * picture would say less, not more. The cost is that they unfurl on X as text
 * rather than as a card, which is the trade this is.
 */
export const OG_IMAGE = {
  url: "/og.png",
  width: 1200,
  height: 630,
  alt: "Chart-recorder paper headed 'US data centres: where they are, what they draw', with the three pen channels named below it.",
};

/**
 * The other half: the page's own address, stated twice because it has to be.
 *
 * Next emits `<link rel="canonical">` from `alternates` and `og:url` from
 * `openGraph.url`, and derives neither from the other — a route that sets only
 * the canonical still ships no `og:url`. X shrugs at that and uses the address
 * it fetched, but LinkedIn reads `og:url`, and its Post Inspector reports the
 * absence rather than filling it in.
 *
 * Spreading OG_BASE here is not decoration. Setting `openGraph` on a route
 * replaces the layout's outright rather than adding to it, so a route that set
 * `url` alone would drop the site name, the locale and the card image — the bug
 * this file's other half exists to explain.
 */
export function routeMeta(path: string): Metadata {
  return {
    alternates: { canonical: path },
    openGraph: { ...OG_BASE, url: path },
  };
}
