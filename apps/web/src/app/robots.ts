/**
 * Everything here is public record, so nothing is disallowed.
 *
 * The file exists for the sitemap line rather than the rules: the county, state
 * and site pages are reachable only through paginated tables, and pointing a
 * crawler at the sitemap is what gets them indexed.
 */
import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

// Required under `output: export`, same as the sitemap route.
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
