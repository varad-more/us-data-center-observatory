/**
 * Region URL helpers and the location of the published data.
 *
 * Split out of `observatory.ts` rather than left there because that module
 * imports `fs` for its build-time reads, and anything a client component
 * touches gets pulled into the browser bundle along with everything it imports.
 * The region picker needs the slug helpers and the data base in the browser, so
 * they live here where nothing Node-only can follow them.
 *
 * `observatory.ts` re-exports all three, so server code carries on importing
 * from the one place it always has.
 */

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "/project-helios";

export const DATA_BASE = process.env.NEXT_PUBLIC_DATA_BASE || `${BASE_PATH}/data`;

/** Turn `county:51107` into the `county-51107` used in URLs and file names. */
export function regionSlug(regionId: string): string {
  return regionId.replace(":", "-");
}

/** Reverse of {@link regionSlug}. */
export function regionIdFromSlug(slug: string): string {
  return slug.replace("-", ":");
}
