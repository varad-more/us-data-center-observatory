# Helios — an observatory for US data-centre growth

**[View the live observatory →](https://varad-more.github.io/project-helios/)**

Helios measures where data centres are, how many appear over time, and how much
power and water they plausibly draw — from public records only, with every claim
carrying the reason it can be believed.

The rule that governs every surface: **an inferred value must never render like a
reported one, and an unknown is never a zero.**

---

## Two datasets, deliberately separate

| | **National observatory** | **Arizona site model** |
|---|---|---|
| Question | How many data centres, where, growing how fast | What is being built on *this* parcel, and how sure are we |
| Grain | 1,853 facilities · 276 counties · 45 states + DC + PR | 13 sites in the East Valley, Maricopa County |
| Storage | committed CSV → JSON → static site | PostGIS + FastAPI, exported to a static snapshot |
| Needs a database | no | yes |
| Refresh | `make poll` | `make bootstrap && make export-api` |

They share a vocabulary and a site, and nothing else. The observatory runs with
no database and no credentials; the site model is the older, deeper study that
the observatory grew out of.

---

## What is measured (snapshot of 2026-07-29)

**Facilities** — 1,853 data centres OpenStreetMap records in the United States:

| Class | Count | Carries a power figure |
|---|---:|---|
| `building` — a mapped structure with a floor plate | 1,506 | yes |
| `site` — a campus mapped as land, not as buildings | 174 | **no** |
| `point` — a location with no geometry at all | 128 | **no** |
| `construction` — mapped as being built | 45 | **no** |

Total mapped building footprint: 19,998,284 m². Only the 1,506 buildings are
sized by area, because land area is not floor area — a 400,000 m² parcel with one
shed on it is not a 400,000 m² data centre.

**Power and water** — LBNL reports 192 TWh of US data-centre electricity for
2024, which is 21,918 MW of average draw. Helios allocates that national total
across the buildings by floor-area share. The allocation sums back to the
published figure exactly; a test enforces it. The result is an `inferred` upper
bound per facility, never a meter reading. Leaders: Loudoun County VA at 239
facilities and 3,034 MW; Virginia statewide at 405 facilities and 4,972 MW.

**Time** — 4,309 OpenStreetMap edit events between 2015-07-11 and 2026-06-19:
1,886 creations, 1,694 tag changes, 509 geometry changes, 220 deletions. This is
a *mapping* curve, not a construction curve. OpenStreetMap carries no build
dates, so Helios never claims one, and the pre-2017 stretch — when the tagging
convention was still being adopted — is shaded and labelled as unqualified on
every chart that shows it. A facility disappearing is reported as "removed from
OpenStreetMap", never as demolished.

**Grid** — 65,325 assets the facilities have to connect to: 48,132 substations
and 17,193 power plants, joined to the same counties. Substation *capacity* is
not published (FERC Form 715 is CEII-restricted), so Helios counts substations
and does not estimate what they can carry.

**Reported loads** — 1 utility filing where an operator's own load figure is on
the public record: MPSC docket U-21990, DTE Electric, 1,383 MW in Saline
Township, Michigan, conditionally approved 2025-12-18. This is the only number
on the site that is `reported` at facility scale rather than inferred.

---

## Assertion classes

Every stored value carries one, surfaced verbatim through the API so the
frontend never re-derives provenance:

| Class | Meaning |
|---|---|
| `reported` | Stated by an authoritative party in a primary source |
| `extracted` | Read out of a document by a parser, with a text span to prove it |
| `calculated` | Deterministically computed from stored values |
| `inferred` | Concluded from indirect signals; may be wrong even when inputs are right |
| `predicted` | A forward projection |
| `unknown` | Not established — rendered as absent, never as zero |

Two things are **never asserted**: when a facility was built, and that a
disappearance means demolition. Neither is in any public source Helios reads.

Sites are named by anonymous project code (`AZ-MESA-001`), never by operator.
Shell-company signals are review flags, not attributions.

---

## Quick start

### The observatory — no database, no credentials

```bash
cd apps/web && npm ci && npm run dev     # http://localhost:3000
```

The dataset is committed as CSV under `data/observatory/` and as JSON under
`apps/web/public/data/`, so a fresh clone runs standalone.

To refresh it from public sources:

```bash
make poll            # OpenStreetMap snapshot + history, then rebuild everything
make poll-grid       # only the substation and power-plant layer
make poll-offline    # rebuild derived files with no network at all
```

CSV is canonical and committed precisely so that `git diff` between two polls
*is* the change log. The writers are byte-stable: a poll with no upstream change
produces no diff, so any diff means real movement.

### The Arizona site model — needs Docker and Python 3.12+

```bash
make install
cp .env.example .env
make db-up            # PostGIS on :5432
make migrate
make bootstrap        # replays recorded fixtures — offline and reproducible
make api              # http://127.0.0.1:8000  (OpenAPI at /docs)
```

`make bootstrap` is offline by default. `make bootstrap-live` fetches current
records from real county and agency servers — opt-in, so a fresh clone, a test
run and CI never put load on public infrastructure.

```bash
helios status                    # what is in the database
helios explain AZ-MESA-001       # why this site scores what it scores
helios backtest                  # replay historical cutoffs against labelled cases
helios registry-show             # every declared source, including unreachable ones
```

---

## Sources

19 sources are declared in `packages/helios_connectors/registry.py`, including
the ones Helios **cannot** reach — with the reason recorded, so a coverage gap
stays visible instead of silently absent. The published
[sources page](https://varad-more.github.io/project-helios/sources/) shows the
blocked and withdrawn ones alongside the live ones.

| Source | State |
|---|---|
| OpenStreetMap power infrastructure (Overpass) | live |
| EPA ECHO air facility records | live |
| Maricopa County Assessor parcels | live |
| City of Mesa building permits | live (address → parcel matching) |
| EIA generation capacity and retail sales by state | live |
| USGS county-level water use | live |
| Michigan PSC large-load contract disclosures | live |
| ACC eDocket | fixture-only — the live UI is session-driven and cannot be scraped responsibly |
| HIFLD electric substations | withdrawn upstream — replaced by OpenStreetMap |
| FERC RM26-4 large-load proceedings | declared as a gap — no machine-readable feed |
| Copernicus Sentinel-2 | declared, not implemented — no credentials, no imagery, no stub |

Helios does not bypass authentication, CAPTCHAs, or any technical access
control, and does not use commercial data-centre directories.

---

## The published site

GitHub Pages cannot run FastAPI, so the deployed site reads flat files. The
observatory JSON is generated from the committed CSVs; the site-model JSON is
generated by the **real API against a fixture-seeded database**, never written by
hand:

```bash
make export-api      # runs the exporter, then verifies the result
make build-web       # static export into apps/web/out
```

CI re-runs the whole bootstrap-and-export cycle to prove the committed snapshot
is still something the pipeline actually produces. Every page carries a banner
saying the deployment is a point-in-time snapshot and when it was taken.

Pages: the national map, per-county and per-state regions, the growth curve,
what changed between polls, construction records, reported utility filings,
sources, methodology, and the Arizona site profiles.

---

## Tests

```bash
make test-unit       # no database required
make test            # full backend suite; needs PostGIS via make db-up
make test-web        # frontend
make check           # everything CI runs: lint + typecheck + test + test-web
make audit-contrast  # every interface colour pair against its WCAG floor
```

The gates that matter are the epistemic ones, and each fails without its fix:
the allocation sums to the published national total; land and construction area
never dilute the buildings; areas are computed on an equal-area projection, not
naive degrees; no serializer ever emits a build date; the pre-2017 band renders
whenever the series reaches back that far *and* stays off a series that does not;
a facility leaving the map is worded as a removal and never as a closure; and a
re-poll with no upstream change produces byte-identical CSVs.

---

## Layout

| Path | Contents |
|---|---|
| `data/observatory/` | the canonical CSVs — facilities, events, regions, series, grid |
| `scripts/observatory/` | fetch, assign, allocate, build — one stage per file, all resumable |
| `apps/web` | Next.js + MapLibre, static export |
| `apps/api` | FastAPI read APIs + token-gated admin routes |
| `apps/worker` | the `helios` CLI |
| `packages/helios_connectors` | registry, connector SDK, fixture replay, pipeline |
| `packages/helios_domain` | ORM models + ontology |
| `packages/helios_scoring` | explainable rules, backtest, impact estimates |
| `packages/helios_geospatial` | clustering, address matching, spatial joins |
| `packages/helios_common` | config, hashing, evidence store, vocabularies |
| `fixtures/` | recorded source payloads — used by the CLI and the tests |
| `database/` | Alembic migrations + PostGIS init |
| `infrastructure/` | Dockerfiles + AWS Terraform scaffolding |

---

## Privacy

`HELIOS_REDACT_NATURAL_PERSON_NAMES` and `HELIOS_REDACT_OWNER_MAILING_ADDRESSES`
suppress private-individual owner names and addresses **before storage**, not as
a display filter. The published deployment runs with both on. Admin routes refuse
to serve at all unless `HELIOS_ADMIN_API_TOKEN` is set — an unset token closes
them rather than leaving them open.

---

## Documentation

| Document | Purpose |
|---|---|
| [`docs/goals.md`](docs/goals.md) | What Helios is for, and what it will not do |
| [`docs/architecture.md`](docs/architecture.md) | System layers and data flow |
| [`docs/methodology.md`](docs/methodology.md) | How assertion classes, allocations and scores are derived |
| [`docs/source-inventory.md`](docs/source-inventory.md) | Every source and its connector status |
| [`docs/limitations.md`](docs/limitations.md) | Honest coverage gaps |
| [`docs/risk-register.md`](docs/risk-register.md) | Known risks |
| [`docs/adr/`](docs/adr/) | Architecture decisions |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Setup, workflow, and invariants to preserve |

**Deliberately absent:** Kafka, Kubernetes, trained ML models, and satellite
pipelines. See [ADR 0002](docs/adr/0002-no-kafka-no-kubernetes.md).

## License

[Apache-2.0](LICENSE)
