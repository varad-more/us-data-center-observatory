# Project Helios — Agent Handoff

**Read this first** before changing code. Companion: [`MULTI_AGENT_SUPPORT.md`](./MULTI_AGENT_SUPPORT.md).

| Field | Value |
|---|---|
| Branch | `cursor/project-helios-observatory-8547` |
| Base | `main` |
| PR | https://github.com/varad-more/project-helios/pull/1 |
| Prior agent run | https://cursor.com/agents/bc-a717266a-57bd-4918-a7b7-33556a138547 |
| Repo | https://github.com/varad-more/project-helios |
| Scope lock | **Phase 0 + first sprint only** — no ML, satellite, Kafka, Kubernetes, or national coverage |
| Tip commit (at handoff) | `5630a89` — Next.js UI, Docker Compose, API integration tests |

---

## 1. What Helios is

Helios Open AI Infrastructure Observatory detects and tracks hyperscale data-center development from **public records**, with every claim carrying an **assertion class** and a path back to an immutable evidence document.

Product rule (non-negotiable): an inferred value must never be rendered like a reported value. Shell-company signals are review flags, never operator attributions.

---

## 2. What works today (MVP state)

Locally runnable stack with real East Valley (AZ) data loaded via `helios bootstrap`:

| Layer | Status |
|---|---|
| PostGIS schema + Alembic (`0001`, `0002`) | Working |
| Immutable evidence store (filesystem / S3) | Working |
| Source registry (13 entries; honesty about gaps) | Working |
| Connector SDK + pipeline | Working |
| Maricopa Assessor connector | **Implemented** (live + fixtures) |
| OSM power / Overpass connector | **Implemented** (live + fixtures) |
| Site clustering + infrastructure dependencies | Working |
| PII redaction (natural-person / mailing) | Working |
| Explainable rule-based scoring + stage history | Working |
| FastAPI (sites, timeline, map, sources, analytics, exports, admin) | Working |
| CLI (`helios …`) | Working |
| Next.js + MapLibre UI | Working |
| Docker Compose + Makefile | Working |
| Unit / contract / integration tests | Substantial (~178 `test_*` defs); e2e folder empty |

**Live demo snapshot** (when DB is bootstrapped): ~13 sites, ~14 parcels, ~175 substations, ~42 evidence records. Flagship profile: **`AZ-MESA-001`** (Platypus Development LLC, ~83 acres, Signal Butte Rd, Mesa) — stage Operational, ~41% confidence, operator **not established**.

```bash
helios status
helios explain AZ-MESA-001
```

---

## 3. Repository map

```
apps/
  api/helios_api/          FastAPI app + routers
  web/                     Next.js 15 + MapLibre frontend
  worker/helios_worker/    Typer CLI (`helios` entry point)
packages/
  helios_common/           config, hashing, evidence store, vocabularies
  helios_domain/           SQLAlchemy models, ontology, sessions
  helios_connectors/       registry, SDK, Maricopa + OSM connectors, pipeline
  helios_geospatial/       site builder, correlation
  helios_scoring/          rules + scoring service
  helios_entity_resolution/
  helios_document_intelligence/
  helios_observability/    mostly placeholder
database/
  migrations/              Alembic
  init/                    PostGIS extensions on first boot
tests/
  unit/ contract/ integration/ fixtures/
  end_to_end/              empty — fill later
docs/                      ← you are here
infrastructure/docker/     API + web Dockerfiles
```

---

## 4. Quick start (next agent)

```bash
# 1. Dependencies
make install                 # .venv + editable install + apps/web npm install
cp .env.example .env         # defaults are fine for local

# 2. Database
make db-up                   # postgres + minio
make migrate
# Ensure helios_test exists for pytest (create once if missing):
#   docker compose exec postgres createdb -U helios helios_test

# 3. Load East Valley data
make bootstrap               # registry-sync → ingest → build-sites → score

# 4. Run
make api                     # http://127.0.0.1:8000  (OpenAPI at /docs)
make web                     # http://localhost:3000   (NEXT_PUBLIC_HELIOS_API_URL)

# 5. Verify
.venv/bin/pytest
cd apps/web && npx tsc --noEmit
```

Admin routes need `HELIOS_ADMIN_API_TOKEN` set; if unset, admin is **refused** (safe default). Compose example often uses `local-dev-token`.

Live fetch kill-switch: `HELIOS_ALLOW_LIVE_FETCH=false`.

---

## 5. Architecture invariants (do not break)

1. **Assertion class is data, not UI.** Persist `reported|extracted|calculated|inferred|predicted|unknown` on facts; UI only badges what the API returns (`helios_common.vocabulary.AssertionClass`).
2. **Evidence is content-addressed and immutable.** Versions keyed by SHA-256; never mutate bytes in place (`helios_common.evidence_store`).
3. **Registry before fetch.** Every source is declared in `packages/helios_connectors/registry.py` with license, rate limit, and access limitations — including sources we cannot read.
4. **Connector honesty.** `IMPLEMENTED` only if live code exists. `FIXTURE_ONLY` only if parser + fixtures exist. `PLANNED` otherwise. Do not invent coverage.
5. **Sites are hypotheses.** Anonymous codes (`AZ-MESA-001`), not company brand names as identity. Clustering = **adjacency AND related ownership** (conservative under-clustering preferred).
6. **Standing conditions ≠ events.** Assessor “DATA CENTERS” classification is a standing condition; do not staleness-punish it like an old deed date.
7. **Historical scoring is opt-in.** `score_site(..., as_of=..., is_backtest=True)` required for past cutoffs — never silently rewrite live stage with a historical replay.
8. **PII redaction on by default.** Natural-person names and owner mailing streets suppressed before persistence.
9. **No Kafka / K8s / ML / satellite in this sprint.** Compose comment references ADRs that are not written yet — write them rather than adding infra.

---

## 6. Bugs already fixed (do not reintroduce)

| Symptom | Root cause | Fix location |
|---|---|---|
| False marker hits (`TR` in `TRAN`) | Substring markers | Word-boundary markers in classify/name code |
| APN merge `30433005S` ↔ `30433005` | Digit-only stripping | Keep alphanumeric APNs |
| APS misclassified as government | `PUBLIC SERVICE` marker | Removed overly broad marker |
| `L.L.C.` broke suffix stripping | Punctuation | Dotted-acronym canonicalize |
| Old deed → zero confidence | Standing condition dated to deed | Multi-evidence + standing exemption in scoring |
| Historical `as_of` downgraded live sites | No backtest flag | Require `is_backtest=True` |
| Zero infrastructure deps after build | Geometry not flushed before spatial SQL | Flush after geometry refresh in site builder |
| Filtered OSM lines counted as rejected | No filtered counter | `items_filtered` column + migration `0002` |
| EPA ECHO shown as implemented | Registry lie | Status set to `PLANNED` |

---

## 7. Known gaps / honesty debt

### Incomplete vs registry

- **`azcc-edocket`** is marked `FIXTURE_ONLY` with entry point `helios_connectors.azcc_edocket:AzccEdocketConnector`, but **`azcc_edocket.py` does not exist**. Either implement fixture-backed parser or downgrade to `PLANNED`. Highest-weight scoring signal is currently unavailable → weak Stage 3 recall / early warning.
- **EPA ECHO** endpoint was probed (Mesa returns facilities); connector not written. Tagged `next-sprint` in registry — best next connector for generator/air-permit signal.
- Assessor exposes **current deed only** → ownership history truncated.
- Score mixes “is this a DC?” with “how far along?” — may need split later; do not paper over with ML yet.
- OSM transmission distances are centroid-approximate.
- Coverage skewed to Stage 7 (assessor already labels existing facilities).
- Phase 0 docs thin: `docs/adr/` is empty; `README.md` is a stub; compose references missing ADR files.

### Out of scope until acceptance criteria for this sprint are closed

Satellite/Copernicus, national expansion, Kafka, Kubernetes, trained models, water-use scenarios, ACC live scraping of stateful ASP.NET search.

---

## 8. Recommended next work (priority order)

1. **Docs debt (this sprint)** — ADRs for no-Kafka/no-K8s and evidence store; fill `README.md` with setup; methodology page already in UI but needs matching backend docs.
2. **Registry honesty** — fix ACC eDocket status vs missing module.
3. **EPA ECHO connector** — highest-value new evidence; two-step QueryID API; spatial match with tolerance.
4. **Mesa building permits** — Socrata; needs trustworthy address→parcel matching in `helios_geospatial.correlation`.
5. **Backtest harness** — historical `is_backtest` path exists; need labelled timelines + metrics.
6. **Frontend tests** — Vitest scaffolding light; add map/timeline smoke tests.
7. **Fill `tests/end_to_end/`** — compose bootstrap → API → one site bundle download.

Do **not** start satellite or ML until 1–3 are in good shape and early-warning sources have a honest path (fixture ACC or live EPA/Mesa).

---

## 9. Key files cheat sheet

| Concern | Start here |
|---|---|
| Stages 0–8 | `packages/helios_domain/ontology.py` |
| Assertion / source enums | `packages/helios_common/vocabulary.py` |
| ORM tables | `packages/helios_domain/models.py` |
| Source inventory | `packages/helios_connectors/registry.py` |
| Connector contract | `packages/helios_connectors/base.py`, `types.py` |
| Ingest pipeline | `packages/helios_connectors/pipeline.py` |
| Site building | `packages/helios_geospatial/site_builder.py` |
| Scoring rules | `packages/helios_scoring/rules.py`, `service.py` |
| API surface | `apps/api/helios_api/main.py` + `routers/` |
| CLI | `apps/worker/helios_worker/cli.py` |
| Fixtures | `tests/fixtures/maricopa_assessor/`, `tests/fixtures/osm_power/` |
| Config knobs | `.env.example`, `packages/helios_common/config.py` |

### Useful API routes

- `GET /health`, `GET /ready`
- `GET /sites`, `GET /sites/{id}`, timeline / evidence / score explanation
- `GET /map/...` GeoJSON layers
- `GET /sources`
- `GET /exports/site/{id}/bundle.zip`
- `/admin/*` — bearer token; refused if token unset

### CLI

```
helios registry-sync | registry-show | ingest | health-check
helios build-sites | score | explain | status | bootstrap
```

---

## 10. Verification checklist before claiming “done”

- [ ] `helios bootstrap` completes without inventing operator identity
- [ ] `helios explain AZ-MESA-001` shows rule contributions + assertion-aware language
- [ ] Map and site detail pages load against live API
- [ ] Evidence bundle zip downloads and references content-addressed docs
- [ ] Registry UI/API shows planned/fixture sources and why
- [ ] `pytest` green; `npx tsc --noEmit` green in `apps/web`
- [ ] No new `IMPLEMENTED` registry entry without a real connector module
- [ ] No Kafka/K8s/ML/satellite added under “just scaffolding”

---

## 11. Environment notes for cloud agents

- Prefer `make` targets; Python **≥3.12**; Postgres 16 + PostGIS 3.4.
- Integration tests use **`HELIOS_TEST_DATABASE_URL`** and drop/recreate schema — never point that at the primary `helios` DB.
- Evidence store default: `./data/evidence-store` (gitignored).
- Screenshots from prior UI verification may exist under `/tmp/shots/` on the prior agent machine — not in git.

When you finish a meaningful chunk: commit on this branch (or a new `cursor/<name>-8547` branch), push, and update PR #1 (or open a focused follow-up PR). Keep handoff sections 6–8 updated if you discover new landmines.
