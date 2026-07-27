# Architecture

Helios is a monorepo with a thin API/UI over domain packages that own provenance.

Provenance is owned by the domain packages, not reconstructed at the edges: the
API serialises stored assertion classes verbatim and the UI badges them without
re-deriving anything.

```text
┌────────────┐   ┌────────────┐
│ apps/web   │──▶│ apps/api   │
│ Next.js    │   │ FastAPI    │
└────────────┘   └─────┬──────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   helios_domain  helios_scoring  helios_geospatial
         ▲             ▲             ▲
         │             │             │
   helios_connectors ──┴─────────────┘
         │
         ▼
   evidence store (FS / S3) + PostgreSQL/PostGIS
```

## Runtime pieces

| Piece | Role |
|---|---|
| `apps/web` | Map, site detail, sources, methodology |
| `apps/api` | Read APIs + token-gated admin mutations |
| `apps/worker` (`helios` CLI) | Registry sync, ingest, build-sites, score |
| `packages/helios_connectors` | Source registry, SDK, connectors, pipeline |
| `packages/helios_domain` | ORM + ontology |
| `packages/helios_scoring` | Explainable rules |
| `packages/helios_geospatial` | Clustering + spatial joins |
| `packages/helios_common` | Config, hashing, evidence store, vocabularies |

## Publishing

The GitHub Pages deployment serves a static snapshot exported from the real API
(`scripts/export_static_api.py`) against a fixture-seeded database. The frontend
reads flat JSON from `apps/web/public/api/`, keyed on project code so published
URLs survive a database rebuild. Nothing about the epistemic model changes in the
export: assertion classes are the ones the pipeline stored.

## Data flow

1. **Declare** sources in `helios_connectors.registry` → `helios registry-sync`.
2. **Ingest** via connector contract: discover → fetch → parse → normalize → validate → load.
3. Pipeline hashes bytes, writes immutable versions, upserts entities, creates evidence only on new versions.
4. **Build sites** clusters parcels (adjacency ∧ related ownership), attaches parcel/permit evidence, links nearby grid assets.
5. **Score** applies weighted rules; every contribution cites one evidence row.
6. **Serve** sites, timelines, GeoJSON, and downloadable evidence bundles.

## Epistemic model

Assertion classes travel with stored facts. The UI must not re-derive whether something was reported vs inferred. See `helios_common.vocabulary.AssertionClass` and `docs/methodology.md`.

## What is deliberately absent

Kafka, Kubernetes, satellite pipelines, and trained ML models — see ADR 0002 and `docs/limitations.md`.
