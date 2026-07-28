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

## Analytical

1. **Score conflates “is a data centre?” with “how far along?”** Rule weights partially separate these, but a single 0–100 score remains a compromise until a labelled backtest exists.
2. **Operator identity is usually unknown.** Shell-company indicators never become operator attributions.
3. **Proximity ≠ service.** Nearby substations are inferred dependencies, not interconnection facts.
4. **Standing vs event evidence.** Mis-dating standing assessor classifications as old deed events previously zeroed confidence; the model now exempts standing conditions from staleness, but other sources must set the flag correctly.
5. **No calibrated probabilities.** Weights are not fitted; confidence bands are display buckets.

## Product / ops

1. Single-container local stack — no Kafka/Kubernetes (ADR 0002).
2. Admin API refuses all mutations when `HELIOS_ADMIN_API_TOKEN` is unset.
3. The published GitHub Pages site is a point-in-time snapshot exported from a fixture-seeded database, not a live view of public records. The date is stated on every page.
