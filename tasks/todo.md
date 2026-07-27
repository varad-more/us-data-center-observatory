# Simplify Helios and make it honestly hostable on GitHub Pages

Direction set by the user: keep the Python backend as the source of truth, publish
a *real* export rather than hand-written mocks, and serve three audiences at once —
portfolio demo, open-source project, and working tool.

## Plan

- [x] **Phase 1 — Offline seeding as a first-class feature**
  - [x] Lift `_replay` out of `tests/` into `packages/helios_connectors/replay.py`
  - [x] Add `FIXTURE_REPLAYS` / `FIXTURE_INGEST_ORDER` / `build_fixture_connector`
  - [x] Move `tests/fixtures/` → `fixtures/` (production code already depended on it)
  - [x] Collapse three duplicate `_replay` definitions onto the package function
  - [x] `helios ingest --fixture`; make `bootstrap --no-live` work; flip default to fixtures
- [x] **Phase 2 — One honest exporter**
  - [x] Delete `scripts/export_mock_json.py` (944 lines of fabricated data)
  - [x] Harden `scripts/export_static_api.py`; key files on `project_code` for stable URLs
  - [x] Export evidence bundles, `sites.csv`, `sites.geojson`, `meta.json`
  - [x] Add `scripts/verify_static_export.py` + `make export-api`
- [x] **Phase 3 — Provenance banner**
  - [x] `DemoDataBanner` reading `meta.json`, rendered from the root layout
  - [x] Route by `project_code`; wire the previously dead download links
- [x] **Phase 4 — CI and infrastructure**
  - [x] Delete `docker.yml`, `smoke.yml`, `docker-compose.yml`
  - [x] `make db-up` → one `docker run postgis`; drop MinIO
  - [x] Rewrite `ci.yml`: offline, PostGIS service, export-reproducibility job, terraform validate
  - [x] Reduce `pages.yml` to an npm-only build; fix the trigger
- [x] **Phase 5 — Dead code and docs**
  - [x] Delete `helios_observability`, `helios_remote_sensing`, Copernicus connector, `SatelliteComparison`
  - [x] Add `LICENSE`, `CONTRIBUTING.md`; rewrite `README.md`; delete agent scaffolding docs
- [x] **Phase 6 — Verification** (see Review)

## Review

### Outcome

| Gate | Before | After |
|---|---|---|
| Test suite | 9 failing / 236 passing | **247 passing, 0 failing** |
| `ruff` / `black` / `mypy` | 145 / fail / 4 errors | **all clean** |
| `npm run lint` | crashed (ESLint 9 vs eslintrc) | **clean** |
| Fresh clone, no DB/extras/env | package unimportable | **148 tests pass** |
| `helios bootstrap` offline | exited 1, "use pytest instead" | **13 sites, 147 evidence** |
| Published data | 944 lines hand-written | **real API export, verified** |

### Bugs found and fixed along the way

All pre-existing; confirmed against baseline `HEAD` by stashing.

1. **`helios_connectors` was unimportable on a default install.** `__init__.py` eagerly
   imported a chain ending at `fitz` (PyMuPDF), which lives in the optional `documents`
   extra. Fixed at the root: lazy import in `pdf_parser`, no eager re-exports.
2. **`assertion_class="estimated"` escaped the closed vocabulary.** `SiteEstimate`
   defaulted to a string that is not an `AssertionClass` member, so the UI could not badge
   it. Power/water estimates apply *assumed* coefficients to measured acreage, so they are
   `inferred`, not `calculated`. Guarded by `tests/unit/test_assertion_vocabulary.py`.
   Only surfaced because we started exporting real data — the mock never emitted it.
3. **Every site published `evidence_count: 0`** while carrying full evidence. The rollup
   query ran before an explicit flush under `autoflush=False`, and per-site inside the
   loop, so a later site claiming evidence left an earlier count stale. Now a single pass
   after all attachments.
4. **Tests did not mirror production session semantics** (`autoflush` on in tests, off in
   production) — which is exactly why bug 3 shipped green. Aligned in `conftest.py`.
5. **Tests could reach a developer's real database** via `get_engine()`. Pinned to the
   test DB.
6. **`AccessMethod.MANUAL_DOWNLOAD` does not exist** (`mesa_agendas.py`) — latent
   `AttributeError`. Corrected to `MANUAL_UPLOAD`.
7. **`DiscoveryResult(warnings=...)` is not a field** (`azcc_edocket.py`) — latent
   `TypeError` on the missing-fixture path.
8. **Nine stale tests** asserting contracts the code had outgrown (single prediction vs
   the identity/stage split; `outcome.score`; a 3-case backtest corpus that had grown to
   5). Updated to assert real behaviour, not weakened.

### Deliberate decisions

- **Byte-identical export diffing was not adopted.** Site UUIDs are random per bootstrap,
  so `git diff --exit-code` could never pass. CI instead rebuilds the export and asserts
  structural truth (flagship present, every advertised site fetchable, counts agree,
  assertion classes valid), then *warns* on drift.
- **Copernicus stays in the registry as `planned` with no connector.** Deleting the
  fixture-backed stub is the honest move: the registry exists to make gaps visible.
- **Terraform and the Dockerfiles were kept** (user's call) — they are a coherent pair,
  since the ECS config deploys those images.

### Known, not addressed (out of scope)

- `helios explain` prints the rules' *implied* stage (4) while the site's persisted stage
  is 7. Pre-existing; a modelling question about which is authoritative, not a defect I
  could resolve confidently.
- `mypy` notes an unused override section for `tests.*`/`scripts.*`. Harmless — it applies
  when mypy is pointed at those trees.
