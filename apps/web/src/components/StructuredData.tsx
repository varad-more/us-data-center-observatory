/**
 * schema.org metadata, emitted as JSON-LD.
 *
 * The `Dataset` block is the one that earns its place. Google Dataset Search
 * indexes `schema.org/Dataset` specifically, and that is a channel aimed at
 * exactly what this site is — a counted, dated, licensed collection of public
 * records — rather than at the generic web search everything else competes in.
 * It also states the licence and the temporal coverage in a machine-readable
 * form, which is the honest thing to publish beside a dataset assembled from
 * other people's data.
 *
 * Every figure here comes from the payloads the pages render, not from a
 * constant, because a structured-data block that disagrees with the page it
 * sits on is worse than none: it is the same claim made twice, differently.
 *
 * `dangerouslySetInnerHTML` is how JSON-LD is emitted; the payload is our own
 * JSON, and `<` is escaped so a string in the data cannot close the tag early.
 */

interface DatasetFacts {
  facilityCount: number;
  lastPolled: string;
  seriesFrom: string | null;
  seriesTo: string | null;
}

const SCHEMA_CONTEXT = "https://schema.org";

/** Escape the one sequence that could break out of a <script> element. */
function serialise(payload: unknown): string {
  return JSON.stringify(payload).replace(/</g, "\\u003c");
}

export function StructuredData({
  siteUrl,
  facts,
}: {
  siteUrl: string;
  facts: DatasetFacts;
}) {
  const graph = [
    {
      "@type": "WebSite",
      "@id": `${siteUrl}/#website`,
      url: `${siteUrl}/`,
      name: "Helios US AI Infrastructure Observatory",
      description:
        "Where US data centres are, how fast they are arriving, and what they draw in electricity and water — counted from public records.",
      inLanguage: "en",
      license: "https://www.apache.org/licenses/LICENSE-2.0",
    },
    {
      "@type": "Dataset",
      "@id": `${siteUrl}/#dataset`,
      name: "US data centres: locations, mapping history, and allocated power and water",
      description:
        `${facts.facilityCount.toLocaleString()} US data centres counted from OpenStreetMap, each at a ` +
        "coordinate, joined to counties and states, with the date each was first mapped and an inferred " +
        "share of the national electricity and water totals published by Lawrence Berkeley National " +
        "Laboratory. Build dates are not asserted: OpenStreetMap carries none, so the time axis is when " +
        "a facility was mapped, not when it was built.",
      url: `${siteUrl}/`,
      license: "https://opendatacommons.org/licenses/odbl/",
      isAccessibleForFree: true,
      creator: {
        "@type": "Organization",
        name: "Helios US AI Infrastructure Observatory",
        url: siteUrl,
      },
      spatialCoverage: { "@type": "Place", name: "United States" },
      ...(facts.seriesFrom && facts.seriesTo
        ? { temporalCoverage: `${facts.seriesFrom}/${facts.seriesTo}` }
        : {}),
      ...(facts.lastPolled ? { dateModified: facts.lastPolled } : {}),
      keywords: [
        "data centers",
        "data centres",
        "electricity consumption",
        "water consumption",
        "OpenStreetMap",
        "electrical grid",
        "United States",
      ],
      distribution: [
        {
          "@type": "DataDownload",
          encodingFormat: "application/geo+json",
          contentUrl: `${siteUrl}/data/facilities.geojson`,
        },
        {
          "@type": "DataDownload",
          encodingFormat: "application/json",
          contentUrl: `${siteUrl}/data/regions.json`,
        },
      ],
    },
  ];

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: serialise({ "@context": SCHEMA_CONTEXT, "@graph": graph }),
      }}
    />
  );
}
