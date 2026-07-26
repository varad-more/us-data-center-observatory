# Architecture

Helios is a monorepo with a thin API/UI over domain packages that own provenance.

**Requirements origin:** the main Project Helios product prompt (see
[`implementation.md`](./implementation.md)). The referenced
`Project_Helios_Architecture.pdf` was not in the workspace; the prompt is
authoritative. This branch completed **Phase 0 + first-sprint / Phase 1 MVP**;
later prompt phases (2–6) are roadmap only.

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
