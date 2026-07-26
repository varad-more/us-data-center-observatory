# Project Helios — Agent Handoff

**Read this first** before changing code. Companion: [`MULTI_AGENT_SUPPORT.md`](./MULTI_AGENT_SUPPORT.md).
**Phase 1 status:** complete — see [`phase-1-acceptance.md`](./phase-1-acceptance.md).

| Field | Value |
|---|---|
| Branch | `cursor/project-helios-observatory-8547` |
| Base | `main` |
| PR | https://github.com/varad-more/project-helios/pull/1 |
| Prior agent run | https://cursor.com/agents/bc-a717266a-57bd-4918-a7b7-33556a138547 |
| Repo | https://github.com/varad-more/project-helios |
| Scope lock | **Phase 1 complete; Phase 2 must not add ML, satellite, Kafka, Kubernetes, or national coverage without a measured need** |

---

## 1. What Helios is

Helios Open AI Infrastructure Observatory detects and tracks hyperscale data-center development from **public records**, with every claim carrying an **assertion class** and a path back to an immutable evidence document.

Product rule (non-negotiable): an inferred value must never be rendered like a reported value. Shell-company signals are review flags, never operator attributions.

---

## 2. Phase 1 capability matrix

| Layer | Status |
|---|---|
| PostGIS schema + Alembic (`0001`, `0002`) | Working |
| Immutable evidence store (filesystem / S3) | Working |
| Source registry (13 entries; honesty about gaps) | Working |
| Maricopa Assessor | **Implemented** |
| OSM power / Overpass | **Implemented** |
| EPA ECHO air | **Implemented** (fixtures for CI; live may 429) |
| Mesa building permits | **Implemented** (address→parcel match) |
| ACC eDocket | **Fixture-only** |
| Site clustering + infra + permit attach | Working |
| PII redaction | Working |
| Explainable scoring + `helios backtest` | Working |
| FastAPI + CLI + Next.js/MapLibre | Working |
| Phase 0/1 docs + acceptance checklist | Working |
| Tests | unit / contract / integration / e2e + Vitest |

Flagship: **`AZ-MESA-001`** (Platypus Development LLC, Signal Butte Rd, Mesa).

```bash
helios status
helios explain AZ-MESA-001
helios backtest
```

---

## 3. Quick start

```bash
make install && cp .env.example .env
make db-up && make migrate && make bootstrap
make api    # :8000
make web    # :3000
.venv/bin/pytest
cd apps/web && npm test && npm run typecheck
```

---

## 4. Architecture invariants (do not break)

1. Assertion class is persisted data, not UI reconstruction.
2. Evidence is content-addressed and immutable.
3. Registry before fetch; no false `IMPLEMENTED` / `FIXTURE_ONLY`.
4. Sites are hypotheses with anonymous codes; cluster = adjacency ∧ related ownership.
5. Standing conditions ≠ events for staleness.
6. Historical scoring requires `is_backtest=True`.
7. PII redaction on by default.
8. No Kafka / K8s / ML / satellite without measured need (ADR 0002).

---

## 5. Recommended Phase 2 work

1. Grow labelled backtest corpus beyond the three East Valley cases.
2. Mesa planning / zoning PDF agendas (document intelligence).
3. Dust-control attribute join if AQD publishes usable fields.
4. Optional score split: “is DC?” vs “stage progression.”
5. Compose CI smoke (full stack bootstrap → bundle.zip).

Do **not** scrape ACC viewstate or add satellite/ML to paper over gaps.

---

## 6. Key files

| Concern | Start here |
|---|---|
| Acceptance | `docs/phase-1-acceptance.md` |
| Stages / evidence kinds | `packages/helios_domain/ontology.py` |
| Registry | `packages/helios_connectors/registry.py` |
| Address matching | `packages/helios_geospatial/addresses.py` |
| Backtest | `packages/helios_scoring/backtest.py` |
| Mesa permits | `packages/helios_connectors/mesa_permits.py` |

CLI: `registry-sync`, `ingest`, `build-sites`, `score`, `explain`, `backtest`, `bootstrap`, `status`.
