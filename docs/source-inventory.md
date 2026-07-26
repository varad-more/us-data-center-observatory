# Source inventory

Authoritative machine-readable registry: `packages/helios_connectors/registry.py`.
Run `helios registry-show` for the live view including access limitations.

| Slug | Status | Role |
|---|---|---|
| `maricopa-assessor-parcels` | **implemented** | Parcel geometry, ownership, DATA CENTERS use code |
| `osm-power-infrastructure` | **implemented** | Substations + HV circuits (ODbL) |
| `epa-echo-air-facilities` | **implemented** | CAA air facilities; backup-generator signal |
| `mesa-building-permits` | **implemented** | Commercial permits; address→parcel match |
| `azcc-edocket` | **fixture_only** | Transmission / substation filings (parser + fixtures; no live ASP.NET scrape) |
| `maricopa-recorder-documents` | planned | Outbound deed links only |
| `maricopa-aqd-dust-control` | planned | Construction earth-disturbance (thin attributes) |
| `mesa-planning-cases` | planned | PDF agendas |
| `srp-infrastructure-projects` | planned | Unstructured utility pages |
| `az-corporation-commission-entity-search` | planned | Privacy review first |
| `sec-edgar` | planned | Operator confirmation from filings |
| `copernicus-sentinel2` | planned | Out of sprint scope (satellite) |
| `adwr-water-records` | planned | Water-use scenarios deferred |

## Implemented connectors

### Maricopa Assessor
- ArcGIS REST, paged, bbox/city bounded.
- Fixtures: `tests/fixtures/maricopa_assessor/`.
- Privacy: owner mailing street not requested; natural-person redaction on normalize.

### OSM power
- One Overpass bbox query per run at 0.5 rps.
- Distribution voltages filtered (`items_filtered`), not counted as failures.
- Absence of OSM features is never negative evidence.

### EPA ECHO air
- Two-step REST: `get_facilities` → `QueryID` → `get_qid`.
- Emits `backup_generator_air_permit` only when NAICS/name/program signals support it.
- Live calls may be rate-limited (300/hour); fixtures cover CI.

### Mesa building permits
- Socrata COM permits, street-filtered to East Valley corridors.
- Address matching via `helios_geospatial.addresses` (exact normalized key).
- Emits `grading_or_construction_permit` evidence.

### ACC eDocket
- Stateful HTML search is not automated.
- Fixture-backed parser produces `substation_application` / `transmission_filing` evidence for recorded dockets.
- Gap remains for *live* early-warning recall until an agency export exists.
