# Limitations

Helios is an early-warning **observatory**, not a complete map of AI infrastructure. Users must treat absence of evidence as a coverage gap unless a source proves a negative.

## Access and coverage

1. **ACC eDocket is fixture-only.** Transmission and substation filings are the highest-weight stage signals, but live search is a stateful ASP.NET UI without a documented API. Helios ships a parser tested against recorded dockets; it does **not** scrape the interactive search. Stage 3 recall is therefore incomplete for projects that only appear in ACC filings.
2. **Assessor history is truncated.** The parcel layer exposes the current deed, not the full transfer chain, so land-assembly timelines understate intermediate buyers.
3. **OSM is incomplete.** Missing substations are not evidence that none exist. Transmission geometries from Overpass `out center` are centroids; distances are approximate.
4. **EPA ECHO rate limits.** The public API throttles aggressive clients. Helios self-limits and uses fixtures in CI; a throttled live run is a temporary gap, not proof of no generators.
5. **Municipal permits and agendas** (Mesa building permits, planning PDFs, dust-control attributes) are not yet automated.
6. **No satellite observations** in this sprint. Copernicus is registered as planned with credentials absent.
7. **Study area is East Valley, Arizona.** National coverage is out of scope.

## Analytical

1. **Score conflates “is a data centre?” with “how far along?”** Rule weights partially separate these, but a single 0–100 score remains a compromise until a labelled backtest exists.
2. **Operator identity is usually unknown.** Shell-company indicators never become operator attributions.
3. **Proximity ≠ service.** Nearby substations are inferred dependencies, not interconnection facts.
4. **Standing vs event evidence.** Mis-dating standing assessor classifications as old deed events previously zeroed confidence; the model now exempts standing conditions from staleness, but other sources must set the flag correctly.
5. **No calibrated probabilities.** Weights are not fitted; confidence bands are display buckets.

## Product / ops

1. Compose stack only — no Kafka/Kubernetes (ADR 0002).
2. Admin API refuses all mutations when `HELIOS_ADMIN_API_TOKEN` is unset.
3. Empty package stubs (`helios_observability`) are placeholders, not monitoring products.
