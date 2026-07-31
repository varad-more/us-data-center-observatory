# Contributing to Helios

Thanks for considering a contribution. This document covers setup, the workflow,
and — most importantly — the invariants that make Helios trustworthy.

## Setup

The fastest useful loop needs no database and no credentials:

```bash
git clone https://github.com/varad-more/us-data-center-observatory.git
cd us-data-center-observatory

python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -m "unit or contract"      # must pass with zero services running
```

Frontend work needs even less — the repo ships a static API snapshot:

```bash
cd apps/web && npm ci && npm run dev
```

### Full environment

Needed for integration tests, the CLI, and regenerating the published snapshot.
Requires Docker.

```bash
make install          # venv + backend extras + npm install
cp .env.example .env
make db-up            # one PostGIS container; creates helios and helios_test
make migrate
make bootstrap        # offline, from recorded fixtures
make test             # full suite
```

## Working offline

**Nothing in the test suite or in CI may touch a live public source.** Helios
reads county assessors, municipal permit portals, and federal APIs — services run
for the public, not for our build matrix.

Recorded payloads live in `fixtures/` and are replayed through the real pipeline
by `helios_connectors.replay`. A replayed connector runs the same parse,
normalize, validate, and load code a live run does; only the network call is
substituted. To add a new fixture-backed source, register it in `FIXTURE_REPLAYS`
in [`packages/helios_connectors/replay.py`](packages/helios_connectors/replay.py).

`helios bootstrap` is offline by default. `--live` is opt-in, and belongs in
manual runs only.

## Checks

```bash
make check      # lint + typecheck + backend tests + frontend tests
make format     # black + ruff --fix
```

CI runs the same checks, plus a job that rebuilds the published snapshot from
fixtures to confirm it is still genuine pipeline output.

## Invariants

These are not style preferences. Breaking one is a correctness bug.

1. **Assertion class is persisted data, not UI reconstruction.** The frontend
   badges the stored string; it must never re-derive whether something was
   reported or inferred.
2. **The assertion vocabulary is closed.** Only the six members of
   `AssertionClass` may reach the database or the API. A value outside it renders
   as an unbadged claim — an inference that no longer looks like one. Guarded by
   `tests/unit/test_assertion_vocabulary.py`.
3. **Evidence is content-addressed and immutable.** Re-ingesting unchanged bytes
   must add nothing — no duplicate document, version, or evidence row.
4. **The registry is declared before the fetch,** and never claims a connector
   status it cannot support. A source we cannot reach stays listed with the
   reason recorded. Do not add a fixture-backed stub to make a gap look filled.
5. **Sites are hypotheses.** Anonymous project codes only. A cluster requires
   adjacency *and* related ownership. Never attribute an operator without a
   direct filing.
6. **Standing conditions are not events.** A current-use classification is dated
   to observation, not to a decade-old deed.
7. **Historical scoring requires `is_backtest=True`,** so a replay can never
   overwrite a site's live conclusion.
8. **PII redaction stays on by default.** Owner names classified as private
   individuals are redacted before storage.
9. **No Kafka, Kubernetes, ML models, or satellite pipelines** without a measured
   need. See [ADR 0002](docs/adr/0002-no-kafka-no-kubernetes.md).

## Tests mirror production

The test session factory uses `autoflush=False` to match
`helios_domain.session`. This is deliberate: with autoflush on, tests see pending
writes the real application would not, which has already hidden one bug where
every site published a zero evidence count while carrying a full evidence trail.
If you change session semantics, change both.

## Changing the published snapshot

`apps/web/public/api/` is generated, but committed — that is what lets frontend
contributors work without a database. Never hand-edit it:

```bash
make db-up && make migrate && make bootstrap
make export-api
```

## Pull requests

- Keep the diff scoped to one concern.
- New behaviour needs a test; a bug fix needs the test that would have caught it.
- If you change what the UI publishes, say how you verified it — a screenshot or
  the exact command you ran.
- Note any invariant you touched and why it still holds.
