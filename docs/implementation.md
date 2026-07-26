# Implementation plan and phase map

This document records the **main product prompt** that authorized Project Helios, the **implementation phases** defined in that prompt, and how this repository executed them. It is the authoritative narrative for “what were we asked to build?” versus “what did we actually ship?”

Companion docs: [`architecture.md`](./architecture.md), [`phase-1-acceptance.md`](./phase-1-acceptance.md), [`methodology.md`](./methodology.md), [`HANDOFF.md`](./HANDOFF.md).

---

## 1. Main prompt (product charter)

### Identity

| Field | Value |
|---|---|
| Project | **Project Helios** |
| Product | **Helios Open AI Infrastructure Observatory** |
| Tagline | *From permit to power-on: transparent early-warning intelligence for AI infrastructure.* |
| Pilot geography | East Valley, Arizona (Mesa, Chandler, Tempe, Gilbert, Queen Creek, Apache Junction + surrounding Maricopa parcels) |

### Goal (from the main prompt)

Design and implement an open, evidence-backed intelligence platform for detecting, tracking, and analyzing the development of hyperscale data centers and AI compute infrastructure.

The system must transform fragmented public-domain information into a **provenance-preserving temporal knowledge graph** that explains how a suspected data-center project progresses from land acquisition through construction, grid connection, energization, and operation.

It is **not** a generic dashboard or static map. It is a research-grade platform with reproducible evidence, explainable predictions, historical backtesting, and measurable performance.

### Core user question

> What evidence suggests that a data center is being developed at this location, what stage is it in, how confident are we, and what physical infrastructure will it require?

### Reference document

The main prompt referenced `Project_Helios_Architecture.pdf` as background. That file was **not present** in the workspace. The prompt instructed:

> Review the reference document before implementation. Preserve its core thesis, but use the requirements in this prompt as the authoritative execution plan.

**This repository therefore treats the main prompt as the authoritative requirements source.** Architecture decisions that would have lived in the PDF are captured here and in ADRs.

### Core product principles (non-negotiable)

As stated in the main prompt (§ CORE PRODUCT PRINCIPLES), condensed:

1. **Evidence before prediction** — every prediction traceable to source records.
2. **Provenance preservation** — URL, org, title, retrieval time, effective date, content hash, parser version, extraction method, snippet, confidence.
3. **Explicit uncertainty** — assertion classes: Reported / Extracted / Calculated / Inferred / Predicted / Unknown.
4. **Temporal modeling** — timelines and stage history, not snapshot-only views.
5. **Reproducibility** — immutable evidence; downloadable bundles.
6. **Explainability** — scores decompose into rule contributions.
7. **Modular ingestion** — independent connectors behind a shared contract.
8. **Historical backtesting** — replay without corrupting live state.
9. **Responsible public data use** — rate limits, licensing, PII posture.
10. **Practical architecture** — do not introduce Kafka, Kubernetes, or distributed infrastructure until measured requirements justify them.

### Two different “stage” vocabularies (do not conflate)

| Vocabulary | What it means | Where |
|---|---|---|
| **Implementation phases** (Phase 0–6) | Roadmap for building the *product* | This document §2 |
| **Development stages** (Stage 0–8) | Lifecycle of a *suspected site* (speculation → operational → expansion) | `helios_domain.ontology.DevelopmentStage`, [`methodology.md`](./methodology.md) |

---

## 2. Implementation phases in the main prompt

The main prompt defined a six-phase delivery roadmap. The table below is the prompt’s intent (not a claim that every phase is done).

| Phase | Name | Prompt deliverables (summary) |
|---|---|---|
| **Phase 0** | Research and design | Source inventory; ADRs; domain ontology; DB schema design; UI wireframes; historical project list; risk register; milestone plan |
| **Phase 1** | Historical observatory | PostGIS schema; source registry; raw evidence store; **3–5 working connectors**; document parsing; parcel ingestion; site/evidence APIs; historical timelines; initial map |
| **Phase 2** | Early-warning engine | Stage model; explainable scoring; continuous scheduling; entity resolution; utility matching; alerts; score history; human review UI |
| **Phase 3** | Remote sensing | Satellite acquisition; parcel change detection; before/after viz; satellite evidence; validation dataset; metrics |
| **Phase 4** | Backtesting and research evaluation | Historical benchmark; time-sliced replay; precision/recall; lead-time; power-estimation accuracy; calibration; research report |
| **Phase 5** | Impact and dependency intelligence | Power estimation; water scenarios; dependency graph; regulatory latency; observability score; regional analytics |
| **Phase 6** | Production hardening | Terraform; AWS; monitoring; CI/CD; security; backup/retention; public docs/demo |

**Original closing instruction:** after the initial design response, begin **Phase 0 and Phase 1**.

### First sprint (nested acceptance slice)

Inside that roadmap, the prompt also defined a **first sprint** whose objective was: foundational data model + one complete evidence-backed site timeline.

First-sprint acceptance criteria (verbatim intent):

- `docker compose up` starts the full local environment  
- Migrations succeed  
- ≥2 connectors ingest real or fixture data  
- Repeated ingestion does not duplicate source records  
- One site on a map  
- ≥5 chronological evidence events, each with provenance  
- Calculated stage + explainable score; score history preserved  
- API docs; backend + frontend tests pass  
- No secrets committed; README with complete setup  

---

## 3. Scope lock that governed this repository

A later instruction narrowed execution:

> Proceed with implementation. **Start with Phase 0 and the first sprint only.**  
> **Do not skip directly to machine learning, satellite processing, Kafka, Kubernetes, or national coverage.**

Immediate objective under that lock:

- Locally runnable system  
- PostGIS + immutable source-document storage  
- Source registry  
- Two (or more) tested/fixture connectors  
- Core site/parcel/org/evidence/stage models  
- Site + timeline APIs, map, one evidence-backed historical profile  
- Explainable confidence  
- Setup docs and tests  
- No fabricated public records (fixtures when live data is unavailable)

That lock remains the **default boundary** for further work unless the product owner explicitly expands it.

---

## 4. How this repo mapped phases to commits

Execution used the prompt’s Phase 0 + first-sprint lock, then closed the remaining first-sprint / Phase-1-schema gaps under the label **“Complete Phase 1.”** That **repo Phase 1** is the *historical observatory MVP for East Valley*, not the entire original Phase 1–6 roadmap.

```text
Main prompt roadmap          What this branch implemented
─────────────────────        ──────────────────────────────
Phase 0  Research/design  →  Done (docs, ADRs, ontology, risk register, inventory)
First sprint / Phase 1 MVP→  Done (see phase-1-acceptance.md)
Phase 2  Early-warning    →  Partially started (stage model + scoring + backtest CLI;
                             not continuous scheduling / full alerts / review UI)
Phase 3  Remote sensing   →  Explicitly out of scope (registry: planned / blocked)
Phase 4  Backtesting R&D  →  Harness only (sparse East Valley cases; no full benchmark)
Phase 5  Impact intel     →  Out of scope
Phase 6  Production       →  Out of scope (Compose-only; ADR 0002)
```

### Phase 0 — completed in this repo

| Prompt ask | Repo artifact |
|---|---|
| Source inventory | [`source-inventory.md`](./source-inventory.md), `helios_connectors.registry` |
| ADRs | [`adr/0001-immutable-evidence-store.md`](./adr/0001-immutable-evidence-store.md), [`adr/0002-no-kafka-no-kubernetes.md`](./adr/0002-no-kafka-no-kubernetes.md) |
| Domain ontology | `helios_domain.ontology`, `helios_common.vocabulary` |
| DB schema | Alembic `0001` / `0002`, `helios_domain.models` (“Phase 1 schema”) |
| Risk register | [`risk-register.md`](./risk-register.md) |
| Milestone / phase map | **This document** |
| UI wireframes | Superseded by shipped Next.js UI (`apps/web`) |

### Repo Phase 1 (MVP / first sprint) — completed

Tracked by [`phase-1-acceptance.md`](./phase-1-acceptance.md). Highlights:

- PostGIS + immutable evidence store + registry  
- Connectors: Maricopa Assessor, OSM power, EPA ECHO, Mesa permits; ACC eDocket fixture-only  
- Site clustering, PII redaction, explainable scoring, `helios backtest`  
- FastAPI (sites, timeline, map, exports) + MapLibre UI  
- Flagship profile `AZ-MESA-001`  
- Tests: unit / contract / integration / e2e + Vitest  

### Later prompt phases — not claimed done

| Phase | Status in this branch |
|---|---|
| Phase 2 (full early-warning engine) | **Partial** — scoring + stage history + admin review endpoints exist; continuous scheduler, alerts product, and rich human-review UI do not |
| Phase 3 (remote sensing) | **Not started** — Copernicus registered as planned; no credentials / no imagery |
| Phase 4 (research evaluation) | **Scaffold only** — `helios backtest` + three labelled cases |
| Phase 5 (impact intelligence) | **Not started** |
| Phase 6 (production hardening) | **Not started** — local Compose only (ADR 0002) |

---

## 5. Implementation order actually followed

1. Monorepo scaffold, Compose, Makefile, config  
2. Ontology + PostGIS schema + migrations  
3. Evidence store + connector SDK + registry  
4. Maricopa Assessor + OSM power connectors (fixtures + live)  
5. Ingestion pipeline, site builder, PII redaction, scoring  
6. FastAPI + CLI + evidence bundles  
7. Next.js map / site / sources / methodology UI  
8. Phase 0 docs (ADRs, architecture, inventory, limitations, risk)  
9. ACC fixture-only honesty + EPA ECHO connector  
10. Mesa permits + address matching + backtest harness + Phase 1 acceptance  

Branch: `cursor/project-helios-observatory-8547` · PR: https://github.com/varad-more/project-helios/pull/1

---

## 6. Exit criteria for claiming “Phase 1 complete”

All items in [`phase-1-acceptance.md`](./phase-1-acceptance.md) are **Met**. Verification:

```bash
make install && cp .env.example .env
make db-up && make migrate && make bootstrap
helios status
helios explain AZ-MESA-001
helios backtest
.venv/bin/pytest
cd apps/web && npm test && npm run typecheck
```

---

## 7. Entering Phase 2 (prompt definition)

Only after Phase 1 acceptance stays green and the owner explicitly opens the next phase. Per the main prompt, Phase 2 targets the **early-warning engine**: continuous ingestion scheduling, stronger entity resolution, utility matching, alerts, richer score history UX, and human review workflows — still without Kafka/K8s/ML/satellite unless a measured need appears (principle 10 / ADR 0002).

Recommended near-term Phase 2 candidates (also listed in HANDOFF):

1. Grow the labelled backtest corpus  
2. Mesa planning / zoning PDF agendas  
3. Dust-control attribute join (if usable)  
4. Split “is DC?” vs “how far along?” scores  
5. Compose CI smoke (bootstrap → evidence bundle)  

---

## 8. Document control

| Item | Value |
|---|---|
| Authoritative requirements | Main Helios product prompt (this agent run); PDF absent |
| Scope lock | Phase 0 + first sprint / repo Phase 1 MVP |
| Status of repo Phase 1 | **Complete** |
| Next prompt phase | Phase 2 (early-warning engine) — not started as a whole |
