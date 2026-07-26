# Phase 1 acceptance criteria

Phase 1 = the locally runnable East Valley observatory described by the Phase 1
schema (`packages/helios_domain/models.py`) and the first product sprint.

**Out of scope for Phase 1:** ML models, satellite/Copernicus, Kafka, Kubernetes, national coverage, ACC live ASP.NET scraping.

## Must-have capabilities

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | PostGIS schema for sources, evidence, orgs, parcels, sites, substations, permits, stages, predictions | Met | Alembic `0001` + `0002` |
| 2 | Immutable content-addressed evidence store | Met | ADR 0001; `helios_common.evidence_store` |
| 3 | Declarative source registry including inaccessible sources | Met | `helios_connectors.registry` + `/sources` |
| 4 | ≥2 live connectors with fixtures | Met | Assessor, OSM, EPA ECHO, Mesa permits |
| 5 | Honest fixture-only path for blocked high-value source | Met | ACC eDocket `fixture_only` |
| 6 | Site/parcel/org/evidence/stage models + clustering | Met | `helios_geospatial.site_builder` |
| 7 | PII redaction for natural persons | Met | Owner classifier + policy flags |
| 8 | Explainable rule-based scoring with contribution rows | Met | `helios_scoring` |
| 9 | Historical replay that cannot mutate live stage | Met | `helios backtest` / `is_backtest=True` |
| 10 | Site + timeline + map + evidence bundle APIs | Met | FastAPI routers + exports |
| 11 | Map UI + site detail with assertion badges | Met | `apps/web` |
| 12 | One evidence-backed East Valley flagship profile | Met | `AZ-MESA-001` (Platypus / Signal Butte) |
| 13 | Docs: architecture, methodology, limitations, ADRs, handoff | Met | `docs/` |
| 14 | Automated tests (unit/contract/integration/e2e) | Met | `pytest` + Vitest |

## Verification commands

```bash
make install && cp .env.example .env
make db-up && make migrate && make bootstrap
helios status
helios explain AZ-MESA-001
helios backtest
helios registry-show
.venv/bin/pytest
cd apps/web && npm test && npm run typecheck
```

## Known Phase 1 limitations (accepted)

Documented in [`limitations.md`](./limitations.md): ACC live gap, assessor deed truncation, OSM incompleteness, ECHO rate limits, score conflation of “is DC?” vs “how far along?”, East Valley–only coverage.

## Exit to Phase 2

Phase 2 may begin only after this checklist stays green and a labelled backtest corpus grows beyond the sparse East Valley cases in `tests/fixtures/backtest/`. Candidates: Mesa planning PDFs, dust-control attribute join, calibration of score split, optional second region — still without Kafka/K8s/ML/satellite unless a measured need appears.
