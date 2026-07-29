# Handoff

For whoever picks this up next. Written 2026-07-29, against `0d118c4`.

Read this, then `tasks/lessons.md`. Everything below is either verified against
the repo today or explicitly flagged as unverified.

---

## What Helios is

Two datasets, built by **entirely different methods**, published as one site.
They must never be used to support each other's claims, and their counts must
never be added together.

**1. The national observatory.** Counts what OpenStreetMap has mapped — 1,853 US
data centres, 48,132 substations, 17,193 power plants — and divides LBNL's
*reported* national electricity and water totals across them. Postgres-free: CSVs
in `data/observatory/` are canonical and committed, scripts build JSON into
`apps/web/public/data/`, the site reads JSON. No server, no database.

**2. The Arizona site model.** Parcel-level inference in one region (East Valley,
AZ) over Postgres + FastAPI, with an evidence chain and a scored confidence
model. This is the older half. **It is not hosted anywhere** — `make export-api`
writes a static snapshot and the published site serves that.

The site is live at `https://varadmore.me/project-helios` (GitHub Pages, static
export, `basePath` `/project-helios`). **The repo itself is currently PRIVATE.**

---

## The one rule that matters more than the rest

**An inferred value must never render like a reported one.** Every surface keeps
these apart:

| Claim | Class |
|---|---|
| This facility is at this coordinate, tagged `telecom=data_center` | `reported` (by OSM contributors) |
| It first appeared in OpenStreetMap on this date | `observed` |
| It was *built* on that date | **never asserted** — OSM carries no build dates (`start_date` coverage is 0%) |
| US data centres used 192 TWh in 2024 | `reported` (LBNL) |
| This facility draws X MW | `inferred` — a share of a reported total |
| It vanished from OSM, therefore it was demolished | **never asserted** — the wording is "removed from OpenStreetMap" |

Tests enforce parts of this. The wording rules in particular: a test asserts the
disappearance string never says "demolished" or "closed". Don't route around it.

The corollary that has already caused a real defect: **an unknown is not a zero.**
A power plant with no capacity tag is counted separately, not summed as zero. A
land parcel gets no megawatt figure at all rather than 0 MW. Follow that pattern.

---

## Working rules (from the user, not derivable from the code)

- **Work directly on `main`.** No feature branches, no PRs. **Pushing `main`
  deploys the live site.**
- **Clean self-contained commits as progress lands**, not one drop at the end.
- Commit messages **describe the real work**. Never phase or sprint numbers.
- Required trailers:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: <session url>
  ```
- Plans go in `tasks/todo.md` with checkable items. After any correction from the
  user, add the pattern to `tasks/lessons.md`.
- **Never mark a task complete without proving it works.** Diff behaviour against
  `main` where relevant; run the thing.
- Local Homebrew `postgresql@14` shadows port 5432 — run the PostGIS container on
  **5433** to verify locally.

---

## State as of this handoff

Everything below was run today.

| Check | Result |
|---|---|
| `make lint` | pass |
| `make typecheck` (mypy 57 files + tsc) | pass |
| `make test-unit` | 225 passed, 199 deselected |
| `make test-web` | 21 passed |
| CI + Deploy to GitHub Pages | both `success` on `125cf6a` |
| Working tree | clean, in sync with `origin/main` |
| Secrets in history | none — no `.env`, `.pem`, or key file in any commit |

`make test` (the full backend suite) needs Postgres and **could not be run
locally — Docker was unavailable.** CI runs it. If you change anything under
`packages/` or `apps/api/`, get Docker up and run it before pushing, or you are
trusting CI to catch what you didn't look at.

### Published dataset

```
facility_count      1853        building_count    1506
construction_count  45          region_count      323
substation_count    48132       plant_count       17193
national_mw         21918       (LBNL 192 TWh / 8760 h, 2024)
total_footprint_m2  19998284    (buildings only)
```

Verified live: `Loudoun County → 3,034.07 MW`, `Virginia → 4,972.44 MW`.

---

## How to run it

```bash
make help                  # every target, described
make check                 # lint + typecheck + test + test-web (what CI runs)
make poll                  # refresh the observatory from public sources, report diff
make poll-offline          # rebuild derived files, no network
make poll-grid             # refresh only substations and power plants
make build-web             # static export into apps/web/out
```

Use `.venv/bin/python`, not `python` — bare `python` is not on PATH here. For the
web workspace use `npm --prefix apps/web ...`; a bare `cd apps/web` in a fresh
shell can trip the permission prompt.

**The pipeline is byte-stable on purpose.** Re-running with no upstream change
produces no CSV diff at all, so `git diff` between two polls *is* the change log.
If you touch a writer, preserve that — stable sort, fixed precision. There is a
test.

**CI does not regenerate `apps/web/public/data/`.** The committed JSON is what
ships. If you change the pipeline, you must re-run it and commit the output, or
the site keeps serving the old numbers while the code says otherwise.

---

## Traps that have already drawn blood

`tasks/lessons.md` has 14 of these written up. The four most likely to bite you:

1. **A shared unit is not a shared quantity** (lessons.md:363). `footprint_m2`
   silently pooled three different physical things — a building floor plate, a
   campus land parcel, and a construction site — and allocating by the pooled
   figure sent 82% of a *measured* national total to geometry that is not a
   building. Nothing structural caught it: conservation passed, figures were
   derived not typed, the pipeline was byte-stable. Only an implausible *ranking*
   exposed it. **The rule: treat an implausible ranking as a defect report about
   the model, not a finding about the world.**

2. **Check the sentinel values a vocabulary reserves** (lessons.md:393). OSM's
   `building=no` is an explicit "this is *not* a building". A first-pass
   classifier used `'building' in tags` and put Valencia County, NM second in the
   nation on six elements, off the back of Meta's 2 km² Los Lunas parcel.

3. **A partial output file can poison every later run** (lessons.md:290). Fail
   loudly rather than write a CSV that looks complete. A throttled Overpass run
   returning zero rows is not evidence of zero data centres.

4. **Reported, delivered and distinct are three numbers** (lessons.md:240). ECHO
   reports 447 rows, delivers 447, and 440 are distinct — its own count includes
   repeated RegistryIDs. Deduplicate on the source's own identifier.

---

## Open work, ranked

### 1. Nobody has ever *looked* at these pages

This is the top item and it is not a code problem. 323 region pages (276
counties, 47 states), the map layers, and the "not mapped as buildings" notice
that renders on 123 of those pages are verified by unit test and by reading
rendered HTML — **never by eye**. A CSS break, an overflowing table,
a broken map on a phone: nothing in the suite would catch any of it. The Chrome
extension has not been connected in any session so far. Ask the user to connect
it, or ask them to click through and report back.

### 2. Decide what "make it public" means

The site is already public. The **repo** is private. Flipping it is clean — no
secrets in history, LICENSE present, `.env.example` holds only non-secret
defaults — but it has no description and no homepage URL set. This is the user's
call, not yours.

### 3. Real gaps in the model, in order of how much they distort published figures

- **A campus mapped only as a land parcel contributes nothing to its county.**
  Racine County, WI holds Microsoft's Mount Pleasant campus across 4.5 km² of
  mapped land and two mapped buildings, so its 30 MW accounts for those two
  buildings and not that campus. Closing this needs a floor-area-to-parcel
  coefficient. **This project has no measured basis for one and will not invent
  it.** Don't fabricate a ratio to make the number look better.
- **45 sites are mapped as under construction** and nothing reads them. This is a
  genuine forward signal — where capacity is being built — and it is currently
  measured, counted, and then ignored. Probably the highest-value unbuilt feature.
- **Cross-check the allocation against a second independent regional figure.**
  The Virginia/JLARC comparison is currently the only external check the model
  has, and it was found after the fact.
- **203 of 1,853 facilities have no `first_seen`** — mapped before the retained
  history begins, so they sit in the counts but in no curve. Each region page
  states its own gap rather than hiding it.

### 4. Loose ends, small

- Two `future-phase` tags in `packages/helios_connectors/registry.py` (lines 424,
  439) — the last of the old phase naming.
- `ConnectorStatus.DEGRADED` and `DISABLED` are states no code can reach.
- `source.notes` renders nowhere, so ADWR's stated deferral reason is held and
  never shown.
- `fixtures/epa_echo/mesa_air_facilities.json` provenance is unresolved; the
  `is_synthetic` column exists and needs setting correctly either way.

`tasks/todo.md` has 27 open checkboxes. **Most are disclosed limitations, not
unfinished work** — they are published on `/methodology` and in
`docs/limitations.md` deliberately. Don't "close" one by deleting the disclosure.

---

## What not to do

- **Don't ingest a commercial data-centre directory**, or a HIFLD mirror. DHS
  withdrew public access to the national substation layer; undated copies survive
  on university ArcGIS servers with empty copyright fields. Substation geometry
  entering the graph as reported fact by way of an unattributed mirror is a worse
  position than OSM's honest under-coverage. The source is registered as
  `withdrawn` so the gap stays visible.
- **Don't estimate substation capacity.** OSM and HIFLD both carry voltage, not
  transformer MW; FERC Form 715 is access-restricted as CEII. It is not publicly
  obtainable at national scale, and nothing in the API or UI carries such a
  figure.
- **Don't tune the confidence weights.** They are domain-reasoned starting points,
  deliberately *not* fitted to outcomes, and calibration is deferred until a
  historical backtest exists to calibrate against. Tuning now produces numbers
  that look authoritative and mean nothing.
- **Don't turn off the privacy redaction.** `HELIOS_REDACT_NATURAL_PERSON_NAMES`
  suppresses assessor owner names classified as private individuals *before*
  anything is written to the database, not as a display filter. The connector
  also declines to request owner mailing addresses at all. The classifier is
  biased toward redaction on purpose.
- **Don't add a per-facility metered power or water figure.** No public source
  meters an individual data centre. Everything published is a share of a reported
  national total, and every such figure is an upper bound of unknown looseness.
