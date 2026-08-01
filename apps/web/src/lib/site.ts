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
