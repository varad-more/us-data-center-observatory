# Helios Open AI Infrastructure Observatory

Evidence-backed detection and tracking of hyperscale data-center development from public records (East Valley, Arizona study area for the first sprint).

Every claim carries an **assertion class** (`reported` / `extracted` / `calculated` / `inferred` / `predicted` / `unknown`) and a path to an immutable, content-addressed evidence document.

## Agent / contributor entry points

| Document | Purpose |
|---|---|
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Current MVP state, invariants, known gaps, next priorities |
| [`docs/MULTI_AGENT_SUPPORT.md`](docs/MULTI_AGENT_SUPPORT.md) | Parallel workstreams, branch protocol, conflict hotspots |
| [`docs/architecture.md`](docs/architecture.md) | System layers and data flow |
| [`docs/source-inventory.md`](docs/source-inventory.md) | Sources and connector status |
| [`docs/limitations.md`](docs/limitations.md) | Honest coverage gaps |
| [`docs/adr/`](docs/adr/) | Architecture decisions (incl. no Kafka/K8s) |

**Scope lock for this sprint:** no ML, satellite, Kafka, Kubernetes, or national coverage.

**Connectors in this sprint:** Maricopa Assessor + OSM power (live), EPA ECHO air (live, fixtures for CI), ACC eDocket (fixture-only parser).

## Quick start

```bash
make install
cp .env.example .env
make db-up
make migrate
make bootstrap          # registry + live/fixture ingest + sites + scores

make api                # http://127.0.0.1:8000  (OpenAPI at /docs)
make web                # http://localhost:3000
```

Or all-in-one via Compose (see `docker-compose.yml`):

```bash
docker compose up --build
docker compose run --rm worker helios bootstrap
```

## Useful CLI

```bash
helios status
helios explain AZ-MESA-001
helios registry-show
helios bootstrap
```

## Tests

```bash
# Requires HELIOS_TEST_DATABASE_URL pointing at a *separate* DB (see .env.example)
.venv/bin/pytest
cd apps/web && npx tsc --noEmit
```

## Layout

- `apps/api` — FastAPI
- `apps/web` — Next.js + MapLibre
- `apps/worker` — `helios` CLI
- `packages/*` — domain, connectors, geospatial, scoring, evidence store
- `database/` — Alembic migrations + PostGIS init
- `tests/` — unit, contract, integration, fixtures

## License

Apache-2.0
