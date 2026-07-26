# Multi-Agent Support Guide — Project Helios

How multiple Cursor agents (or humans) can work this repo **in parallel without corrupting provenance, registry honesty, or each other’s branches**.

Primary context: [`HANDOFF.md`](./HANDOFF.md) and [`implementation.md`](./implementation.md) (main prompt + Phase 0–6 map). Scope lock: Phase 0 + first sprint / repo Phase 1 — **no ML, satellite, Kafka, Kubernetes, or national coverage** unless explicitly expanded.

---

## 1. Operating principles

1. **One owner per vertical.** An agent owns a workstream end-to-end (code + tests + docs notes), not a random file sprinkling.
2. **Merge via git, not chat.** Shared truth is the branch / PR. Do not assume another agent’s uncommitted working tree.
3. **Small PRs over mega-diffs.** Prefer `cursor/<workstream>-8547` feature branches off `main` (or rebase onto latest `cursor/project-helios-observatory-8547` if that MVP PR is still open).
4. **Registry is a mutex.** Only one agent changes `packages/helios_connectors/registry.py` at a time; others wait or coordinate via sequential commits.
5. **Schema is a mutex.** Alembic migrations are strictly serial. Never two agents autogenerating migrations in parallel.
6. **Honesty over demo.** Never mark a connector `IMPLEMENTED` or `FIXTURE_ONLY` to make a dashboard look fuller.
7. **Do not expand scope** to close a gap. If early warning is weak, say so and add a planned source — do not scrape ACC viewstate or add satellite “just for the pitch.”

---

## 2. Workstream board (assign one agent each)

| ID | Workstream | Owns (paths) | Depends on | Definition of done |
|---|---|---|---|---|
| **A** | Docs & Phase 0 | `docs/**`, `README.md`, ADRs | None | README runnable; ADRs for evidence store + no-Kafka/no-K8s; limitations page accurate |
| **B** | Registry honesty + ACC fixture | `helios_connectors/registry.py`, new `azcc_edocket.py`, `tests/fixtures/azcc_*`, contract tests | A (limitations text) optional | Status matches code; fixture parser tested **or** status downgraded to `PLANNED` |
| **C** | EPA ECHO connector | New `epa_echo.py`, fixtures, contract + integration tests, registry status→`IMPLEMENTED` | B done or not touching same registry lines | Live + fixture ingest; evidence linked to sites; scoring rule wired if needed |
| **D** | Geospatial address match + Mesa permits | `helios_geospatial/correlation.py`, Mesa connector, site_builder hooks | C optional (independent) | Address→parcel matches with tests; permits produce Stage 4-ish evidence when warranted |
| **E** | Scoring clarity + backtest | `helios_scoring/**`, scoring tests, CLI explain polish | Stable evidence from C/D | Documented separation of “is DC?” vs “stage”; backtest path exercised in tests |
| **F** | API / export polish | `apps/api/**`, `tests/integration/test_api.py` | Domain stable | Contract tests for new fields; bundle.zip still self-contained |
| **G** | Frontend | `apps/web/**` only | API schemas stable (coordinate with F) | Typecheck clean; assertion badges correct; no fabricated operators in UI copy |
| **H** | QA / e2e | `tests/end_to_end/**`, Makefile smoke targets | A–G slices merging | Compose bootstrap → API → web smoke documented and automated where cheap |

**Conflict hotspots** (serialize access):

- `packages/helios_connectors/registry.py`
- `packages/helios_domain/models.py` + `database/migrations/versions/*`
- `packages/helios_scoring/rules.py` (rule IDs / weights)
- `apps/api/helios_api/schemas.py` (frontend contract)
- `docker-compose.yml` / `.env.example`

---

## 3. Branch & PR protocol

```text
main
 └── cursor/project-helios-observatory-8547     # MVP umbrella (PR #1) — stabilize then merge
      ├── cursor/helios-echo-connector-8547     # example child workstream
      ├── cursor/helios-mesa-permits-8547
      └── cursor/helios-phase0-docs-8547
```

Rules:

- Branch names: `cursor/<descriptive-kebab>-8547` (lowercase).
- Prefer **rebase or merge from latest umbrella/main** before opening PR.
- PR title: `[Helios] <workstream>: <outcome>`.
- PR body must state: **scope**, **sources touched**, **how to verify**, **explicit non-goals**.
- After push: update the PR description if acceptance criteria changed; keep `HANDOFF.md` §8 current if priorities shifted.
- Do not force-push shared umbrella branches another agent may be based on unless coordinated.

---

## 4. Handoff packet (paste into the next agent prompt)

Use this template when spawning or resuming an agent:

```markdown
## Helios assignment
- Workstream ID: <A–H>
- Branch: cursor/<name>-8547
- Base: main (or cursor/project-helios-observatory-8547 if MVP unmerged)
- Read first: docs/HANDOFF.md + docs/MULTI_AGENT_SUPPORT.md
- Scope lock: no ML, satellite, Kafka, Kubernetes, national coverage
- Do not edit: <list conflict hotspots you don't own>

## Goal
<one paragraph outcome>

## Done when
- [ ] <testable bullet>
- [ ] pytest relevant paths green
- [ ] registry status matches code (if connectors)
- [ ] HANDOFF.md §8 updated if priorities changed

## Forbidden
- Marking connectors implemented without modules
- Silent historical score overwrites (need is_backtest=True)
- Committing .env secrets, node_modules, .next, evidence blobs
```

---

## 5. Parallelism patterns that work

### Safe parallelism

| Agent 1 | Agent 2 | Why safe |
|---|---|---|
| G Frontend | C EPA connector | Different trees; freeze OpenAPI fields or use additive JSON |
| A Docs | H QA scripts | Docs don’t change runtime |
| E Scoring unit tests | D correlation (until wiring) | Touch different packages until integration |

### Unsafe parallelism (avoid)

| Pair | Why |
|---|---|
| Two migration authors | Alembic heads diverge |
| Two registry editors | Status/entry-point conflicts; honesty bugs |
| Scoring rule renames + frontend copy of rule IDs | Broken explanations |
| Site builder clustering rewrite + permit linker | Double-counting parcels / sites |

If blocked on a hotspot: finish the smaller change, merge, then start the larger one.

---

## 6. Shared contracts (freeze these unless versioned)

Agents consuming these must treat changes as **breaking** and notify workstream F/G:

1. **AssertionClass** string values (`helios_common.vocabulary`).
2. **DevelopmentStage** integers 0–8 (`helios_domain.ontology`).
3. **Site project codes** format `AZ-<CITY>-NNN`.
4. Evidence bundle zip layout under `/exports/site/{id}/bundle.zip`.
5. Map GeoJSON property names used by `InfrastructureMap.tsx`.
6. Connector pipeline summary fields (`items_filtered` vs rejected).

Additive fields are preferred over renames. If you must rename: migrate API + frontend + tests in **one** PR.

---

## 7. Testing expectations per workstream

| Change type | Minimum tests |
|---|---|
| New connector | Contract tests against fixtures; optional live marked so CI can skip |
| Registry status change | Assert status enum in a unit/contract test or registry snapshot test |
| Scoring rule | Unit tests for contribution math + standing-condition / staleness cases |
| Site clustering | Integration test with fixture parcels |
| API schema | `tests/integration/test_api.py` cases |
| Frontend | `tsc --noEmit`; component test if logic is non-trivial |
| Migration | `alembic upgrade head` + `alembic check` on clean DB |

Never point `HELIOS_TEST_DATABASE_URL` at the primary `helios` database.

---

## 8. Communication norms (async)

When an agent finishes a turn that affects others, leave artifacts **in git**, not only in chat:

1. Update `docs/HANDOFF.md` §6 (new landmines) and §8 (priority queue).
2. Add a short note under `docs/notes/` only if needed for a multi-day investigation (`docs/notes/YYYYMMDD-<topic>.md`). Prefer HANDOFF updates over note sprawl.
3. PR description = source of truth for reviewers.
4. Do not reply on external threads (Slack/Linear/GitHub issue comments) unless the user explicitly asked.

---

## 9. Escalation / stop conditions

**Stop and document** (do not “push through”) when:

- A live source’s ToS/robots clearly forbids the planned access pattern.
- Personal data fields beyond the current redaction policy would need to be stored.
- Two agents discover contradictory site identities for the same parcels.
- Scoring would require labelling that does not exist (temptation to add ML) — write the labelling plan instead.
- ACC / municipal HTML requires brittle viewstate automation — keep `FIXTURE_ONLY` / `PLANNED` and explain the gap.

---

## 10. Suggested first split after this MVP PR

If spawning three agents immediately:

1. **Agent A (docs)** — README + ADRs + keep HANDOFF accurate.
2. **Agent B (ACC honesty)** — remove false `FIXTURE_ONLY` or implement fixtures.
3. **Agent C (EPA ECHO)** — next evidence source; touch registry only after B merges, or take registry ownership alone.

Frontend (G) waits until C/D expose new evidence types worth displaying, unless fixing UX bugs on existing pages.

---

## 11. Quick commands every agent should know

```bash
make install && make db-up && make migrate && make bootstrap
make api    # :8000
make web    # :3000
.venv/bin/pytest
.venv/bin/helios status
.venv/bin/helios explain AZ-MESA-001
.venv/bin/helios registry-show
```

Admin: set `HELIOS_ADMIN_API_TOKEN` or expect `/admin` to refuse.

Live network off: `HELIOS_ALLOW_LIVE_FETCH=false`.
