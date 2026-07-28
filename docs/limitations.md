# Limitations

Helios is an early-warning **observatory**, not a complete map of AI infrastructure. Users must treat absence of evidence as a coverage gap unless a source proves a negative.

## Access and coverage

1. **ACC eDocket is fixture-only.** Transmission and substation filings are the highest-weight stage signals, but live search is a stateful ASP.NET UI without a documented API. Helios ships a parser tested against recorded dockets; it does **not** scrape the interactive search. Stage 3 recall is therefore incomplete for projects that only appear in ACC filings.
2. **Assessor history is truncated.** The parcel layer exposes the current deed, not the full transfer chain, so land-assembly timelines understate intermediate buyers.
3. **OSM is incomplete.** Missing substations are not evidence that none exist. Transmission geometries from Overpass `out center` are centroids; distances are approximate.
4. **EPA ECHO rate limits.** The public API throttles aggressive clients. Helios self-limits and uses fixtures in CI; a throttled live run is a temporary gap, not proof of no generators.
5. **Mesa planning agendas and dust-control attributes** are not yet automated. Commercial building permits are ingested with address-only matching (no coordinates in source).
6. **No satellite observations.** Copernicus Sentinel-2 is declared in the registry as `planned` with no connector at all. A fixture-backed satellite stub was deliberately removed rather than kept, because shipping one would have implied an imagery capability Helios does not have.
7. **Only one region is actually read.** `helios_domain.regions` names nine US regions; exactly one — East Valley, Arizona — is `ACTIVE`. The rest are `DECLARED`: in scope, and empty. A region appearing in the registry is not a claim that Helios is watching it. The two hard blockers to minting a site elsewhere (an `AZ-` project-code prefix and a `Maricopa` county default) are removed, but no connector reads another region yet.
8. **National EPA ECHO coverage is a query, not a pipeline.** The ECHO connector can sweep every state in one request via the `p_ncs` NAICS filter (`helios ingest epa-echo-air-facilities --nationwide`), which returns roughly 380 hosting-classified air facilities across the US. Those facilities are not sites. They land as permit rows with coordinates, and site building attaches permits to sites *by proximity* — so outside the pilot region, where no parcels have been ingested and therefore no sites exist, they stay unlinked. Parcel coverage is the blocker, and it is per-county: every county publishes its assessor data differently, or not at all.
9. **Area totals are published at two different resolutions, and on different clocks.** EIA's retail sales file currently stops at 2020 while its generation capacity file runs to 2024, so two figures sitting side by side describe different years. Each carries its own `reference_year` rather than being aligned, because matching another dataset's staleness is worse than showing the gap.
10. **Resolution mismatch between water and electricity.** USGS gives water withdrawals per county; EIA gives retail electricity sales per state and no public source breaks those sales to county nationally. A statewide denominator is much weaker than a county one for a metro-scale region, and it understates the local share of any figure compared against it. Every stored row carries its own `area_kind`, and the API returns the mismatch as an explicit note rather than papering over it.
11. **The water total is 2015 and there will not be a newer one soon.** USGS publishes county-level water use on a five-yearly cycle, but the 2020 compilation dropped the county breakdown entirely. 2015 is the most recent county figure that exists, not the most recent Helios bothered to fetch. Comparing a present-day site estimate against it is comparing across a decade.
12. **Helios does not know substation capacity and will not estimate it.** HIFLD and OSM both carry substation voltage; neither carries transformer capacity in MW, and FERC Form 715 is access-restricted as CEII. Substation MW capacity is not publicly obtainable at national scale. No substation in the API or the UI carries a capacity or a utilisation number, and none will be invented to fill the gap.
13. **State generating capacity is not headroom.** Helios publishes what a state can generate, not what is spare. Existing demand already consumes most of it, and how much is not in any source Helios reads. A site's share of total capacity therefore says nothing about whether that site can be connected — that is an interconnection question settled by filings Helios cannot access.

## Analytical

1. **Score conflates “is a data centre?” with “how far along?”** Rule weights partially separate these, but a single 0–100 score remains a compromise until a labelled backtest exists.
2. **Operator identity is usually unknown.** Shell-company indicators never become operator attributions.
3. **Proximity ≠ service.** Nearby substations are inferred dependencies, not interconnection facts.
4. **Standing vs event evidence.** Mis-dating standing assessor classifications as old deed events previously zeroed confidence; the model now exempts standing conditions from staleness, but other sources must set the flag correctly.
5. **No calibrated probabilities.** Weights are not fitted; confidence bands are display buckets.
6. **Helios's share of an area total is a ratio of an inference to a measurement.** The denominator is reported and whole-area, covering every existing user. The numerator is inferred from acreage for sites that in most cases are not built, and the electricity comparison layers an assumed load factor on top of an already-assumed power density in order to turn a capacity into an annual energy figure. The ratio gives a sense of scale. It is not a forecast of what the area will consume, and it is weaker than either number that goes into it.

## Product / ops

1. Single-container local stack — no Kafka/Kubernetes (ADR 0002).
2. Admin API refuses all mutations when `HELIOS_ADMIN_API_TOKEN` is unset.
3. The published GitHub Pages site is a point-in-time snapshot exported from a fixture-seeded database, not a live view of public records. The date is stated on every page.
