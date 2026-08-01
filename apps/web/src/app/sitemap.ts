/**
 * The sitemap, built from the same sources the pages are.
 *
 * Nearly every URL here is a county, a state or a site — the long tail that a
 * reader actually searches for ("Loudoun County data centres"), and the part a
 * crawler is least likely to reach on its own, since those pages are linked
 * from paginated tables rather than from navigation. Enumerating them by
 * calling the same helpers the routes call means the sitemap cannot list a page
 * that was not built, or miss one that was.
 *
 * `lastModified` is the poll date, not the build clock. The site is rebuilt on
 * every push, including pushes that change no data, and telling a crawler that
 * 352 pages changed because a stylesheet did is a claim the bytes do not
 * support. It is the same reason `meta.json` publishes `last_polled` rather
 * than a `generated_at` wall clock.
 */
import type { MetadataRoute } from "next";

import { listSites } from "@/lib/api";
import { getObservatoryMeta, getRegions, regionSlug } from "@/lib/observatory";

import { SITE_URL } from "@/lib/site";

// Required under `output: export`: without it Next treats the route as
// server-rendered and refuses to build, since a static host has nothing to run.
export const dynamic = "force-static";

/** Routes that exist regardless of what the data contains. */
const STATIC_ROUTES = [
  "",
  "/growth",
  "/regions",
  "/construction",
  "/large-load-filings",
  "/observatory-map",
  "/changes",
  "/sites",
  "/map",
  "/analytics",
  "/understand",
  "/methodology",
  "/sources",
];

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [meta, regions] = await Promise.all([getObservatoryMeta(), getRegions()]);

  // The Arizona study is exported separately and may be absent from a fresh
  // checkout. Its pages are then not built, so they must not be listed either.
  const sites = await listSites({ limit: 500 }).catch(() => null);

  const lastModified = meta.last_polled || undefined;

  const urls = [
    ...STATIC_ROUTES,
    `/regions/${regionSlug("national:US")}`,
    ...regions.map((region) => `/regions/${regionSlug(region.region_id)}`),
    ...(sites?.items ?? []).map((site) => `/sites/${site.project_code}`),
  ];

  return urls.map((path) => ({
    url: `${SITE_URL}${path}/`,
    lastModified,
  }));
}
