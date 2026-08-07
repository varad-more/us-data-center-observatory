# Redesign the UI/UX along the lines of the Affordability Index

Direction set by the user: review `Tech-affordability-index` (published as
`varad-more/affordability-index`), take its design language, and apply it here.
Ivory default with a dark toggle; assertion class re-encoded as an ordinal ramp
plus a border treatment. Repo rename deferred; the US-scope data expansion is a
separate program.

## Repository audit

Asked whether the repo is production-ready and whether anything in it is
garbage. Two defects found, both shipped and both fixed here.

- [x] **The published national growth curve was stale and 4% high.**
      `region_series.csv` was written once and never rebuilt, while `events.csv`
      later lost 155 unplaced rows. Because `_regions_of` only credits a county
      when the row carries one, the loss fell entirely on `national:US` — 322 of
      323 series were correct, and the wrong one was the headline. 1,736 against
      a true 1,666 in June 2026.
- [x] **`poll.py --skip-fetch` logged a poll it had not performed.** A row in
      `poll_log.csv` asserting the source was checked, when nothing was
      contacted.
- [x] Test the wording gate the README had to disclaim: a disappearance renders
      as "removed from OSM", never as closed, decommissioned or shut down.
      Verified by mutation — swapping the label to "closed" fails the test.

### What the audit found clean

614 tracked files, no `__pycache__`, `.pyc`, `.DS_Store`, build output or editor
leftovers among them. No `.env`, key material or credential-shaped strings. No
`TODO`/`FIXME`/`XXX` markers. The only empty tracked files are `__init__.py`
package markers, `.gitkeep` and `.nojekyll`. `.git` is 8.5 MB.

393 of the 614 are generated payloads — 330 region series, 57 static API files,
the observatory JSON. They are committed on purpose: GitHub Pages has no build
step for them, and CI does not regenerate `apps/web/public/data/`. That is also
exactly why the stale-series defect above could survive, so the trade has a
cost and it has now been paid once.

### Closed since

- [x] **Nothing in CI regenerated derived data**, so an input change could leave
      the published series stale again the same way. Now a job runs the offline
      rebuild and diffs the result, failing the build on any drift. An mtime
      comparison was the obvious shape and would have been wrong: git does not
      record mtimes, so every file looks equally fresh in a clean checkout. The
      content comparison works because the writers are byte-stable, which is a
      property the project already guarantees and tests.
- [x] **`meta.json` carried a wall-clock `generated_at`**, the one field that
      changed on a run that changed nothing. It quietly falsified the
      byte-stability claim and had to go before any drift gate could exist. Now
      `last_polled`, read from the last `poll_log.csv` row.
- [x] **The crawler's User-Agent pointed at a repository that does not exist.**
      Volunteer-run APIs use that string to reach whoever is loading them.

- [x] **Renamed to `us-data-center-observatory`** and moved onto its own
      subdomain, `us-data-center-observatory.varadmore.me`. `project-helios`
      matched nothing anyone would search and collided with a NASA probe and a
      Kubernetes operator. The custom domain also removed the base path: Pages
      serves a custom domain from the host root, so the `/project-helios` prefix
      every asset URL carried had to go, not merely change.

### Still open

Making the repo public is still undecided. Nothing ranks in search while it is
private, so the rename buys nothing until that call is made.

## Repository presentation: description, README, commit history

- [x] Set the GitHub description and 16 topics. The repo is still **private**;
      the Pages site is public. Making the repo public is a separate decision
      and has not been taken.
- [x] Rewrite `README.md`. It still described Helios as an Arizona-only parcel
      study, so the observatory — the larger dataset by two orders of magnitude
      — was invisible to anyone arriving from the repository page. Every figure
      in the new text is read off `data/observatory/` and
      `apps/web/public/data/meta.json`, not remembered.
- [x] Squash 89 commits into 24 linear milestones. Built with `git commit-tree`
      from each milestone's own tree rather than by rebase, so every commit is a
      state the repo genuinely occupied and no conflict resolution invented one.
      The `Merge pull request #2` commit is flattened; the graph has no merges.
      Original author dates are preserved. A first pass at 14 was rejected as
      too coarse — it buried the scoring split, the ECHO sweep and the
      allocation fix inside larger commits.

### Review

`git diff <new-head> <old-head>` is empty, `git rev-list --parents` shows no
commit with two parents, and each of the 24 commit trees hashes identically to
the milestone tree it was built from. Re-verified on the rewritten tree:
`make lint`, `make typecheck`, `make test-unit` 234 passed, `make test-web` 31
passed.

The pre-squash history is kept locally as branch `backup-pre-squash` and tag
`backup/pre-squash`; neither is pushed. Deleting them discards the only copy of
the 89-commit history, so leave them until the rewritten `main` has been live
long enough to trust.

One README claim was cut rather than published: nothing tests that a
disappearance is never worded as a demolition. The wording is enforced by
`apps/web/src/app/changes/page.tsx` and its comment, and the plan called for a
test that was never written. A README about provenance is the last place to
assert a gate that does not exist.

## Codebase review and cleanup

Asked for a review of what is done and what remains, plus a cleanup. The repo
was not in the state `tasks/handoff.md` recorded: 56 files sat staged and
uncommitted, holding four separate bodies of work.

- [x] Split the staged blob into four self-contained commits, each buildable on
      its own. The nav entries in `layout.tsx`, `SiteFooter.tsx` and `page.tsx`
      had to be split by hand so no commit links to a page that does not exist
      yet.
- [x] `ObservatoryMap` sized a feature with no `site_class` as a building. All
      1,853 published features carry the class today, so the branch was
      unreachable — but the default was backwards, and an unknown is not a
      building. Both layers now partition on `!= "building"`, and a test pins it.
- [x] Delete nine public helpers with a definition, an `__all__` entry and no
      caller. Keep `OrganizationRelationship`: `0001_initial_schema.py` creates
      the table, so removing the model would be schema drift.
- [x] Remove `packages/helios_remote_sensing`, which held only stale bytecode
      and was never tracked.
- [x] Correct four statements in this file that the work below had already
      superseded — the Virginia 2,255 MW figure, and "nothing yet reads" the
      construction records.

### Review

Verified on the final tree: `make lint`, `make typecheck` (mypy 58 files +
tsc), `make test-unit` 234 passed, `make test-web` 31 passed.

**`make test` was not run.** Docker is unavailable on this machine, so the
integration and contract suites that need PostGIS on 5433 have not executed
locally — including `tests/contract/test_mpsc_large_load_connector.py`, which is
new. CI runs them. Anyone pushing this is trusting CI for that half.

The intermediate commits were verified by construction rather than by checking
each one out: every split file's earlier state is a strict subset of its final
state with no dangling identifier. The registry-tag commit was the exception and
was run directly — 7 passed.

Still not done, and still the top item: nobody has looked at any of these pages
in a browser.

## Construction signal and visual audit

Started after the 2026-07-29 handoff. The first browser pass covered the live
landing page, a county page with both campus and construction exclusions, and
the national map at desktop and phone widths. It exposed one remaining version
of the footprint conflation: the map and the named-facility table still called
every polygon area a building footprint.

- [x] Size only building marks by floor plate on the national map; draw land
      parcels and construction records at a fixed size.
- [x] Label each mapped area for the physical thing it measures in map popups
      and region tables.
- [x] Correct the national map's "building outline mapped" percentage so it
      counts buildings, not every polygon with an area.
- [x] Publish the 45 records mapped as under construction as a forward signal,
      without turning their mapped area into MW or their first OSM appearance
      into a construction-start date.
- [x] Link the new surface from the landing page, navigation, and footer.
- [x] Prove the map interaction, web tests, typecheck, lint, static export, and
      representative desktop/mobile layouts.

### Review

The live visual audit covered the landing page, Maricopa County and the national
map before implementation. The new static export was then checked at desktop
width and 390 × 844: the construction page has no page-level horizontal
overflow, its two wide tables scroll inside their cards, and the corrected map
renders and still loads its grid on demand.

The defect was broader than one table label. The national map reported 93% as
"building outline mapped" by counting every record with any polygon area, even
though only 1,506 of 1,853 records (81%) are buildings. It also used campus land
and construction area to size those marks. Both now use `site_class`: buildings
scale by floor plate, everything else is a fixed-size point, and popups name the
quantity they display.

The new `/construction` surface publishes 45 current construction-tagged
records across 20 counties and 15 states. It names the 23.01 km² total as mapped
construction geometry, assigns no MW or water, and describes `first_seen` only
as the record's first appearance in retained map history.

Verification:

- `make lint` — pass
- `make typecheck` — pass
- `make test-unit` — 225 passed, 199 deselected
- `make test-web` — 26 passed
- `make audit-contrast` — every light and dark pair clears its floor
- `make build-web` — 352 static pages generated, including `/construction`

## Show source registry notes

The registry, database, API schema, static export and frontend Zod schema already
carry `source.notes`. The sources page is the only layer that discards it, which
leaves ADWR's stated deferral reason and several source-specific interpretation
notes invisible.

- [x] Render registry notes separately from access limitations.
- [x] Add a component test proving both fields survive when a source has both.
- [x] Verify the committed static payload already carries ADWR's note, so no
      database-backed re-export is needed.
- [x] Run web lint, typecheck, tests and the static build.

### Review

`apps/web/public/api/sources.json` already carries eleven non-empty registry
notes, including ADWR's "Needed before any water-use scenario is published.
Deferred." The API router and Zod schema both already require the field. The
only change needed was to stop dropping it in the source-entry component.

Notes now render as contextual registry prose, while an `access_limitation`
keeps its own caution notice. They are not aliases: one explains why a source
matters or how to read it; the other explains why Helios cannot access it.

Verification:

- web lint — pass
- web typecheck — pass
- web tests — 28 passed, including both note-only and note-plus-limitation cases
- static build — 352 pages generated

## Register the federal large-load interconnection gap

FERC opened RM26-4 in October 2025 and issued six tailored RTO/ISO show-cause
orders on 18 June 2026. Those proceedings are primary evidence that future
large-load study and cost data may become public, but they are not a uniform
machine-readable dataset today. The NYISO order is the specific order that
describes a searchable public location for aggregate requests, network upgrades,
and cost estimates; the registry must not generalize that exact remedy to all
six operators.

- [x] Add the FERC proceeding as a planned utility/regulatory source, dated and
      linked to the official RM26-4 page.
- [x] Expose each source's publisher URL from the rendered registry, rather
      than carrying `base_url` only in JSON.
- [x] State that the six orders are tailored and that no uniform ingestible
      regional dataset exists yet.
- [x] Add an honesty test that prevents the planned proceeding from acquiring a
      connector or being described as current coverage.
- [x] Regenerate the published source catalog through registry sync and the
      static API exporter.
- [x] Verify backend and web behavior, then close the two corresponding
      candidate/cleaning items below.

### Review

The registry and generated `/sources` payload now carry 18 entries. FERC is
listed as `planned`, with no connector, no successful run and zero documents.
Its public note separates the six tailored proceedings from the more specific
NYISO publication proposal, while its access limitation says plainly that
Helios has no current interconnection coverage.

The source was synced into the fixture database and exported through the real
API rather than added by hand to `sources.json`. The rendered `/sources` page
links the official proceeding and shows both the registry note and access
limitation.

Verification:

- `make check` against PostGIS on port 5433 — 427 backend tests and 28 web tests
  passed; lint and both typecheckers passed
- `make export-api` — 13 sites and 18 sources exported; snapshot verifier passed
- `make audit-contrast` — every light and dark pair clears its floor
- `make build-web` — 352 static pages generated
- `git diff --check` — pass

## Publish a state large-load filing

The first bounded state-PUC implementation is Michigan MPSC Case U-21990. The
Commission's 18 December 2025 disclosure names DTE Electric, Green Chile
Ventures, Saline Township and a 1,383 MW contracted data-centre load. It is a
site-specific primary regulatory statement, unlike Pennsylvania's statewide
model tariff, but it locates the project only to a township. Helios should
publish the filing and the reported number without inventing a parcel or map
point.

- [x] Register the MPSC disclosure as an implemented, fixture-replayable public
      source.
- [x] Parse the recorded official page into one cited large-load service
      contract, preserving the 1,383 MW text and its reported assertion class.
- [x] Publish filing-level API and web output with township location precision,
      immutable document provenance and no inferred geometry.
- [x] Add connector, API and frontend contract tests for the epistemic and
      location invariants.
- [x] Rebuild the fixture database and static export, visually inspect the new
      surface, and run the complete verification suite.

### Review

MPSC U-21990 is now a first-class filing record rather than an Arizona site or
national map point. The connector replays the captured official Commission
page through the production parser, emits one `large_load_service_contract`
evidence record, preserves 1,383 MW as `reported`, and carries Saline Township
as the most specific location with no geometry.

`GET /large-load-filings` and the new `/large-load-filings` page publish the
docket, named contracting parties, stated parent relationship, decision date,
reported load, exact source snippet, retrieval time and content digest. The
page explicitly distinguishes contracted demand from operating consumption,
generation capacity and available grid capacity. It does not call Oracle the
operator.

Browser inspection caught a fixture placeholder URL in the first rendered
draft. Fixture replay now retains the official MPSC URL, unchanged-document
ingestion refreshes the logical document's checkable URL while preserving each
immutable version URL, and static verification rejects a placeholder URL. The
same inspection caught and removed a duplicated “County” label. At a 1280 px
viewport the page has no horizontal overflow.

Verification:

- `make check` against PostGIS on port 5433 — 436 backend tests and 30 web tests
  passed; lint and both typecheckers passed
- static export verifier — 13 Arizona sites plus one provenance-complete
  large-load filing; no filing geometry; official source URL retained
- `make audit-contrast` — every light and dark pair clears its floor
- `make build-web` — 353 static pages generated, including
  `/large-load-filings`
- in-app browser DOM and layout inspection — official link, assertion badge,
  township precision and no-point notice all rendered; no horizontal overflow
- `git diff --check` — pass

## Plan

- [x] **Tokens and typeface** — warm ivory ground, `light-dark()` throughout,
      documented contrast rationale per token, Fraunces via `next/font/local`
- [x] **Theme toggle** — persisted, guarded `localStorage`, blocking pre-paint script
- [x] **Assertion class → ordinal ramp** — plus `data-evidence-basis` and its guard test
- [x] **Construction stage → sequential ramp** — legend derived from the ramp,
      theme-aware basemap, MapLibre popup restyled
- [x] **Page chrome** — serif hero with an eyebrow, footer generated from the
      source registry, freshness line
- [x] **Accessibility** — contrast audit wired into CI, print styles,
      `prefers-reduced-motion`, focus rings
- [x] **Greyscale verification** — see Review

## Review

### What changed, and why it is not just a restyle

The interface encoded two *ordinal* quantities as unrelated categorical hues.
Assertion class ran sky → emerald → violet → amber → pink → slate; construction
stage ran an eight-hue rainbow. A rainbow on ordered data implies categories where
there is a progression, and it left colour carrying a distinction it cannot carry
alone. Both now run along one sequential ramp.

The assertion re-encoding had to *strengthen* the product rule, not dilute it, so
the distinction is carried by three independent channels:

| channel | carries | survives greyscale |
|---|---|---|
| the word | the class itself | yes |
| the basis | observed / derived / unestablished | yes — solid, dashed, dotted |
| the ramp | degree | partially |

The basis moved out of CSS into the component as `data-evidence-basis`. It had
been three separate `border-style: dashed` declarations — an invariant nobody can
see and any restyle could drop one of, and dropping one makes an inferred value
look observed.

### Verification

| Gate | Result |
|---|---|
| `lint` / `typecheck` / `test` / `build` | clean after every commit |
| Assertion guard test | **proved** — flipping `inferred` to observed fails 2 cases |
| Contrast audit, both themes | 7 failures found and fixed; now all clear |
| Greyscale separation | ramp monotonic in both themes; 1 collapse found and fixed |
| Static export | all routes pre-render; both basemap variants ship |

### Bugs and design faults found along the way

1. **Badge borders at the pale end of the ramp failed 3:1** (1.73 and 2.49). These
   were the borders on `predicted` and `inferred` — one of the three encoding
   channels — so the encoding was silently collapsing to fill colour alone.
   Solving each step to the floor individually pushed them onto nearly the same
   value, so the badge edges got their own ramp solved across 3.05:1–9.5:1.
2. **`unknown` and `predicted` were the same mark in greyscale** (luminance 0.292
   vs 0.288). Both passed the contrast audit; the collapse only showed up when
   measuring the classes against each other. Fixed structurally with a dotted
   edge rather than by moving a colour.
3. **The map legend had already drifted from the map** — it held its own copy of
   the stage hex values and claimed stage 7 was gold where the map drew it amber.
   The legend now reads out of the ramp.
4. **`--unmeasured-edge` failed 3:1** in both themes (2.19, 1.81).
5. **The light wordmark measured 4.48:1** against a 4.5 floor.
6. **Testing Library's cleanup was never registered.** It self-registers only
   under `globals: true`, which this project does not use, so renders accumulated
   in the document and any second test querying a testid found two of them. The
   pre-existing single test passed only because it was alone in the file.

### Deliberate decisions

- **Amber survives as `--brand`, confined to the wordmark.** Helios is the sun and
  the identity is worth keeping, but the moment it grades a value it becomes a
  second data hue — which is what the palette exists to avoid.
- **Badge labels take `--ink-1`, never a ramp step.** Ramp steps are marks held to
  3:1; as ink under 11px type they owe 4.5:1 and the pale end does not reach it.
  Contrast lives in the text, grading in the fill and edge.
- **The footer is generated from the source registry.** A hand-typed list is free
  to drift toward claiming a source that is not feeding anything.

### Known, not addressed

- **The basemap is still a third-party request.** Tiles come from
  `basemaps.cartocdn.com`; the reference project makes a point of shipping its map
  from its own repository. Self-hosting tiles is real work and separate from a
  visual redesign.
- Node-20-deprecated action versions in the workflows.
- Four "phase" leftovers in the tree (migration filename, `models.py` docstring,
  `backtest.py` report title, ADR 0002).

---

## National base layer (track 6)

Goal: make a site outside Arizona *possible*. Not to claim one exists.

- [x] Region registry (`helios_domain/regions.py`) — slug, state code, counties,
      cities and bbox in one place, validated at import.
- [x] `generate_project_code` takes its state prefix from the region.
- [x] Removed the `"Maricopa"` / `"east-valley-az"` column defaults.
- [x] `build_sites` takes a region rather than a city tuple and a slug that were
      free to disagree.
- [x] EPA ECHO industry mode — `p_ncs` NAICS filter, one request nationwide.
- [x] `/regions` endpoint + coverage table on `/sources`.
- [x] Root-caused the CI failure the defaults had been hiding.

### What the two hardcodes were actually costing

`generate_project_code` prefixed every code with `AZ-`, and `Site.county`
defaulted to `Maricopa`. Not "the national work hasn't started" — a site built
in Loudoun County would have been minted claiming to be in Arizona, and nothing
would have flagged it. Both are gone; a region must now be named.

### Verified, not assumed

ECHO's NAICS filter is `p_ncs`. `p_naics` is accepted, silently ignored, and
returns the unfiltered set: 480 rows for Arizona against 15 for the real filter.
Measured against the live API before any code was written. Nationwide by hosting
NAICS returns 384 facilities in one request; Virginia alone returns 121.

### The gap this exposes

The ECHO connector can now read the whole country, and it does not help yet.
Facilities land as permit rows and are attached to sites *by proximity*; outside
the pilot region there are no parcels, so there are no sites, so they stay
unlinked. **Parcel coverage is the blocker, and it is per-county** — every county
publishes its assessor data differently, or not at all. That is the next real
piece of work, and it is a connector per county, not a flag.

### Deliberate

- Nine regions registered, one `ACTIVE`. A `DECLARED` region is in scope and
  empty, `/regions` publishes its site count, and a unit test asserts only
  east-valley-az is active — so the list cannot quietly become a coverage claim.

---

## Area consumption — the measured denominator

Goal: give Helios's inferred per-site figures something reported to sit against.

- [x] `area_consumption` table, keyed on the measurement rather than a source id.
- [x] `sector` non-null with an `"all"` sentinel — a nullable column inside a
      unique constraint is not constrained in Postgres.
- [x] USGS county water connector (2015, Mgal/d, per county FIPS).
- [x] EIA state electricity connector (xlsx, MWh/yr, per state).
- [x] County FIPS on every region, read out of the USGS file itself.
- [x] Registry entries, replay fixtures, CLI wiring, bootstrap in live mode.
- [x] `/analytics/area-consumption` — reported totals and inferred comparisons
      as two separate lists.
- [x] `annualise_power_mwh` with a published load factor.
- [x] Frontend panel on `/analytics`, two cards with opposing badges.
- [x] Rounded the summed estimates — an unrounded `func.sum()` was drifting in
      its last bit between exports and reaching the published snapshot.

### The granularity mismatch is real and is surfaced, not smoothed

Water is published per county. Electricity is published per state, and no public
source breaks retail sales to county nationally. Averaging or apportioning the
state figure to a county would have produced a number that looked better and
meant less. Every row carries its own `area_kind` and the API returns the
mismatch as an explicit note.

### What made the comparison hard to state honestly

A site estimate is a *capacity* in MW. A retail sales total is *energy* in
MWh/yr. Turning one into the other needs an assumed load factor, which sits on
top of the assumed power density already inside the capacity figure. The result
is weaker than its own input. It is published as a band with the load factor
named, in a list the API keeps separate from the reported totals.

### Verified against the real files

Maricopa 2015 public supply 776.54 Mgal/d, total withdrawal 2,058.19, population
4,167,947. Arizona 2020 retail sales 81,960,074 MWh/yr, and the four sectors sum
to it — which is the check that catches reading EIA's overlapping provider
categories and double counting.

### Supply side: generation capacity

- [x] `area_consumption` renamed to `area_totals` (migration 0005). It already
      held county population, which is not a consumption; the name was for the
      first thing that went in, not for what the table means.
- [x] EIA existing-capacity connector — nameplate and net summer, per state.
- [x] Third comparison: summed site MW against reported summer capacity.

That third comparison is the strongest of the three and the easiest to misread.
Strongest because both sides are a peak figure in MW, so it needs no conversion
at all — one assumption fewer than the annual-energy one. Easiest to misread
because 1.68% of state capacity invites "there is plenty of room", and it is
nothing of the sort: existing demand already consumes most of that figure and
Helios does not know how much. The caveat says so and two tests assert it.

Arizona, as published: 32,876.5 MW net summer capacity (2024) against
81,960,074 MWh of retail sales (2020). Those years do not match because EIA's
own files do not, and each is shown with the year it describes.

### Grid coverage: HIFLD substations

- [x] Established that the source no longer exists publicly, and recorded it.
- [x] `ConnectorStatus.WITHDRAWN` added, so the registry can say "taken away"
      rather than "not built yet".
- [x] Root-cause fix: status and access limitation moved onto `sources`
      (migration 0006).

The plan called for HIFLD's national substation layer as the upgrade over
contributor-dependent OSM coverage. It is gone. The HIFLD Open catalogue API
answers `401 — private org id ... is not accessible`, and nothing federal
replaced it: the EIA Energy Atlas catalogue (89 datasets) carries no substation,
transmission or power-plant layer at all. What survives are copies on university
and state-agency ArcGIS servers — undated snapshots with empty copyright fields
and no maintained licence.

Not ingested, deliberately. Substation geometry entering the graph as reported
fact by way of an unattributed mirror is a worse position than OSM's honest
under-coverage, which at least has a live licence and a contributor history.

Recording it surfaced a real bug. The API read `connector_status` and
`access_limitation` off `source_connectors`, and a connector row exists only
when a registry entry names importable code — so the sources with no access at
all had nowhere to carry their reason, and reported themselves as `planned`.
Five of six declared limitations never reached a reader: Copernicus, SRP, the
ACC entity search, the county recorder and HIFLD. The registry had been keeping
its most important field to itself. Both fields now live on the source.

Live coverage summary: 7 implemented, 7 planned, 2 fixture-only, 1 withdrawn.

Follow-up not taken: three planned sources (`sec-edgar`,
`maricopa-aqd-dust-control`, `adwr-water-records`) still declare no limitation.
They are unbuilt rather than blocked, so that is arguably correct, but ADWR's
`notes` field explains the deferral and the sources page renders `notes` nowhere.

---

## What to do next — a survey of the field, and what it changes

Goal: decide where Helios goes now that comparable public trackers exist, and
stop guessing at what is already solved elsewhere.

### The landscape

Six comparable efforts, none of which existed in this form when Helios started:
DataCentersExposed (6,098 sites, 45 countries), dcmap.us (4,800 US facilities),
the Data Center Atlas (2,353, each tied to a permit or filing), FracTracker
(media monitoring plus FOIA), Compute Atlas (725 facilities, open source with a
public API, citing permits, tax abatements, water filings and queues), and
PNNL's IM3 atlas (existing *and projected*, with fiber, water and transmission
layers).

Helios has 13 sites in one Arizona valley. **On coverage this is not a contest
and should not become one** — which is what `docs/goals.md` already says by
listing completeness as a non-goal. What none of the six do is carry a per-claim
assertion class resolving to an immutable evidence document. Two of them cite
sources per *facility*; none distinguishes "a party filed this" from "we derived
this" at the level of the individual number. That is the differentiator, and it
survived contact with the field.

### Candidate work, ranked

- [ ] **State PUC large-load dockets.** The live replacement for the dead ERCOT
      track. Michigan's MPSC approved a 1.4 GW special contract for a hyperscale
      site in Saline Township; DTE then filed a Large Load Provision for loads
      over 100 MW; Pennsylvania created a dedicated large-load tariff. These are
      primary filings carrying a **reported** MW figure attached to a named
      site — the exact epistemic object track 1 wanted, reachable today.
- [x] **Register FERC RM26-4 as a planned source.** On 18 June 2026 FERC issued
      tailored show-cause orders to all six jurisdictional RTOs/ISOs. The NYISO
      order specifically proposed publication of large-load network upgrades,
      costs and zonal aggregates in a searchable location. Nothing to ingest
      uniformly yet; a registry entry citing the docket makes the gap visible
      and dated, which is what the registry is for.
- [ ] **GASB 77 tax abatement disclosures.** Every state and local government
      must disclose taxes abated in its annual financial statements. No tracker
      ties public cost to a specific site, and 14 states do not disclose
      data-centre incentive costs at all — a nameable gap of exactly this
      project's genre.
- [ ] **LBNL "Queued Up".** Project-level queue data from 50+ operators covering
      ~98% of US capacity, as Excel with a codebook. It is *generation*, not
      load: it strengthens the supply half of the grid-balance comparison and
      does not answer demand. Do not let the name suggest otherwise.
- [ ] **Locational uncertainty in the geometry.** The Data Center Atlas draws an
      exact point for a confirmed address, a soft halo for city-or-county-level
      placement, and nothing at all for unconfirmed sites. Helios badges values
      but draws geometry as if always exact. This is the map-level form of the
      rule the whole project runs on.
- [ ] **Treat the other trackers as claims to check, not as truth.** Ingest them
      as third-party assertions and publish the disagreement — "three trackers
      assert a facility here, Helios finds no permit". Measuring inter-source
      disagreement is a product none of them can offer, because none model claim
      provenance. Compute Atlas is the licence-viable one.

### Cleaning, sorted by whether a reader is misled

- [x] `source.notes` renders nowhere, so ADWR's stated deferral reason is held
      and invisible — the same defect just fixed one field over.
- [x] The interconnection gap is asserted in `limitations.md` twice,
      `methodology.md`, the analytics caveat and two source comments, and the
      registry says nothing. The page built to show gaps omits the biggest one.
- [x] Two `future-phase` tag values in `registry.py` — removed rather than
      renamed, because `PLANNED` already carries delivery posture and tags should
      describe the source.
- [x] `ConnectorStatus.DEGRADED` and `DISABLED` were statuses no code could
      produce. Dropped them and closed the vocabulary with a reachability test.
- [ ] Three stale claims in "Known, not addressed" above: the Node-20 actions
      are already on v5–v7, and three of the four "phase leftovers" are clean.

### The parcel hypothesis, tested and rejected

Worth recording because it was wrong twice before it was right.

The recorded blocker is "a connector per county, not a flag". The hypothesis was
that this overstates the cost, because counties largely publish through two
platforms with uniform APIs, so the shape should be one connector per *platform*
plus a per-county config row. Measured, in order:

1. ArcGIS Hub's dataset API returns 245,034 datasets matching "parcels", and
   Loudoun County's parcel layer answers a plain ArcGIS REST query with acreage,
   parcel id, update date and geometry — no bespoke code. Encouraging.
2. That service publishes **no ownership table** (layers: parcel boundaries,
   address points, subdivisions). Helios clusters on adjacency *and* related
   ownership, never adjacency alone, so the layer Helios can reach is the one it
   cannot cluster from.
3. A probe of eight counties for "parcels" found ownership in none — but
   Maricopa was among them, and Helios demonstrably reads `OwnerName` from
   `gis.maricopa.gov/.../RED/Assessor/MapServer`. The probe was searching the
   wrong word: ownership rides on layers named *Assessor* or *Tax Parcel*.
4. Re-probed for those terms, six of eight counties appeared to expose
   ownership — and the result is noise. "Loudoun" and "Fairfax" both matched a
   **Charlottesville** layer, "Santa Clara" matched a *streets* layer with an
   `owner` field, "Dallas" matched a third-party republication by a private
   firm, and Maricopa — the one county known to work — returned nothing.

So the conclusion already in `docs/limitations.md` stands, and the hypothesis
does not. The refinement worth keeping is narrow: the *transport* is frequently
the same ArcGIS REST API Helios already speaks, so the per-county cost is
discovery, layer identification and field mapping rather than a new HTTP client.
That is a real saving and it is not a flag.

The sharper finding is a hazard. Automated discovery by keyword returns
wrong-jurisdiction layers and third-party republications that are
indistinguishable from authoritative ones at the API surface. A discovery-driven
connector would have ingested a private firm's copy of Dallas County parcels as
county-authoritative — the same failure as the HIFLD mirrors, arrived at by a
different road. Per-county identification has to stay a human decision that
names the authoritative endpoint.

## National coverage — what shipped, and what it cost to find

Helios now reads one source nationally and still builds sites in one region. That
asymmetry is the product, not a shortfall, and both halves are published side by
side so neither can be read as the other.

**Shipped**
- [x] Nationwide ECHO sweep recorded as a fixture (440 distinct facilities, 39
      states) and replayed in `bootstrap`, so the published snapshot rebuilds offline.
- [x] `/analytics/national-coverage` and `/map/facilities`, plus the coverage panel
      and the continental map that render them.
- [x] `docs/limitations.md` items 7 and 8 rewritten: national is now a pipeline,
      not a query, and "read" is defined as *sites*, not *records*.

**Three defects the national query exposed, all invisible in one state**
1. `responseset` is ECHO's page size and was set to `1`, with only page one ever
   fetched. A query matching 447 facilities returned one row. City result sets hid
   it because ECHO sometimes embeds a first page — and whether it does varies
   between identical requests.
2. Classification read `FacNAICSCodes`; the national payload carries `AIRNAICS`
   and no `Fac*` columns whatsoever. Measured: 7 rows kept of 59 before, 54 after.
3. Address and jurisdiction were built from a literal `"AZ"` and a default of
   `"Arizona"`. Nationally that writes a fabricated location onto a *reported*
   field, which is the specific failure this project exists to prevent.

Each now has a test that fails without its fix.

**A distinction worth keeping.** ECHO reports 447 rows, delivers 447, and 440 are
distinct: its headline count includes repeated RegistryIDs. The first version of
the fix compared the de-duplicated total against the headline and announced a
coverage gap that did not exist. Delivery and uniqueness are different facts and
are now reported as different facts.

### Open: is the pilot ECHO fixture a recording or a construction?

`fixtures/epa_echo/mesa_air_facilities.json` has four rows whose RegistryIDs are
`110070123456`, `110070654321`, `110011112223`, `110044455566` — sequential digit
runs, unlike every real ECHO identifier — and whose names read like deliberate
keep/filter cases (`PLATYPUS CAMPUS EMERGENCY GENERATORS` against `DESERT READY
MIX PLANT 7` and `CITY WELL SITE 12 BACKUP ENGINE`). The national recording does
*not* contain them; at that same address it carries `PLATYPUS DEVELOPMENT`,
RegistryID `110062853416`, which is a real record.

This matters because both sets now publish under one source with nothing to tell
them apart, and two of the four hand-shaped rows attach to East Valley sites as
`reported` federal facts.

It is **not** resolved, and was deliberately not acted on. A live check against
`p_city` returned zero rows under HTTP 429, and zero-rows-because-throttled is
not evidence of absence — the same trap as the county-parcel probe above. Deleting
published evidence on an unconfirmed inference is worse than leaving it one more
release.

- [ ] Re-run the Mesa/Chandler city query against ECHO when not rate-limited and
      confirm whether those four RegistryIDs exist.
- [ ] If they do not: stop ingesting the fixture in `FIXTURE_INGEST_ORDER` (keep it
      for contract tests, which is what it is good for) and re-export. The real
      Arizona records already cover both affected sites, so nothing real is lost.
- [ ] Either way, set `is_synthetic` where it belongs. The column exists on
      `Permit` and every ECHO row currently reads `False`.

**Not a finding, and worth writing down as a corrected assumption.** `PLATYPUS
DEVELOPMENT LLC` looked like anonymisation and is not: it is the real assessor
owner of APN 30433005S, and EPA lists `PLATYPUS DEVELOPMENT` at the same address.
It is a genuine shell company of exactly the kind the scoring rules exist to
notice. The assessor fixture is real throughout — `DIGITAL 2121 SOUTH PRICE LLC`
sits at 2121 S Price Rd, where ECHO independently reports `DIGITAL REALTY TRUST
CHANDLER`.

## The pivot: a data-centre growth observatory

The project's centre of gravity moved from deep inference in one Arizona valley
to broad measurement across the country over time. The existing site model is
kept as a sub-part, not retired.

### What shipped

- [x] 1,853 US data centres from OpenStreetMap, pinpoint coordinates, 92% with
      building footprints, 62% with a named operator
- [x] 4,464 mapping events, 2012 to June 2026 — 1,967 appearances, 232 removals
- [x] National curve: 135 mapped data centres at end-2016 to 1,736 in June 2026
- [x] 276 counties and 47 states, each with its own monthly series and page
- [x] LBNL's reported 192 TWh and 17.4 bn gallons allocated by footprint; state
      shares re-sum to 21,918 MW exactly
- [x] `make poll` — one resumable command, byte-stable, reports what changed
- [x] Changes feed, national map, growth chart with the pre-2017 band hatched

Validated against a direct ohsome query made before any of the code existed:
2016 135 v 136, 2023 917 v 916, 2025 1,520 v 1,518.

### Known gaps, deliberately left visible

- [ ] 2 tiles with no current facility were never checked. Only a data centre
      mapped there and since removed could hide in them.
- [ ] 203 of 1,853 facilities have no `first_seen`: mapped before the retained
      history, so they are on the map but not in any curve. Each region page
      states its own gap rather than hiding it.
- [ ] Superseded, kept for the record: Virginia was allocated 2,255 MW against
      JLARC's ~4,100 MW for Northern Virginia alone, and this was read as
      footprint under-weighting dense multi-storey halls. The cause was the
      pooled-area defect, not storeys; allocating on building floor area put
      Virginia at 4,972 MW. See the measured table below. What remains open is
      the opposite error: regions mapped campus-first are now understated.
- [ ] Facility coverage is unmeasurable. No authoritative count of US data
      centres exists to compare 1,853 against.

### Worth doing next

- [ ] Cross-check the allocation against a second independent regional figure
      (Dominion's metered Northern Virginia load) and publish the error, the way
      the backtest harness does for the scoring model.
- [ ] Per-facility footprint history, so the footprint curve stops attributing
      today's enlarged buildings to the month they were first drawn.
- [ ] A `--since` incremental poll is written but has never run against a real
      upstream change; exercise it once ohsome is healthy.

## Making the site readable by someone who did not build it

The landing page was still the pre-pivot page: it opened on "East Valley,
Arizona · Maricopa County" and never mentioned the national observatory at all.
A visitor arrived at the sub-part and had no way to discover the main work —
no link to /growth, /regions, /changes or the national map existed above the
fold or anywhere else on it. The nav was a flat strip of ten items mixing two
different datasets, with "National map" and "Site map" sitting beside each
other meaning entirely different things.

The second gap: the site published numbers but never explained the subject.
Nothing said what a data centre is, why electricity is the binding constraint,
why water is spent at all, or what a megawatt means next to a county.

- [x] Rewrite `/` to lead with the observatory: headline figures, the national
      curve, where they concentrate, what changed, and a guide into each
      section. Arizona becomes a clearly-labelled second dataset.
- [x] Group the nav into observatory / Arizona study / reference, and rename
      the two "map" entries so they cannot be confused.
- [x] Add `/understand`: the theory — anatomy of a data centre, why power and
      water, why they cluster, how to read every number here, glossary.
- [x] Extend `/methodology` to cover the observatory pipeline, which was
      documented in the repo but nowhere on the site.
- [x] Rebuild the footer around the same three groups.
- [x] Tests for the claims that must not regress, then lint, typecheck, build.

### What the rework delivered

The entry point now leads with the observatory, and the path from the front
page to any of the nine pivot pages exists. Verified live: 10,135 internal
links across 349 built pages, none broken; 351 pages export; 11 web tests,
five of them new and covering the one property that must never regress — the
pre-2017 stretch of the growth curve stays hatched and labelled.

Two figures were wrong in draft and are worth remembering as a pattern. A
hardcoded "4.4%" sat beside a dynamically resolved year, which is the 2023
share next to the 2024 total. And a 30:1 footprint spread was carried over
from one county's numbers; measured nationally it is 263:1. Both are now
derived from the committed CSVs at build time. The worked example that
converts 192 TWh into a continuous 21,918 MW reaches the same figure the
allocation uses by a different route, which makes the explanatory text
checkable against the data rather than merely consistent with it.

Not verified: nothing was ever looked at. The Chrome extension is not
connected, so the check was structural — rendered HTML, heading outlines,
the link graph, the contrast audit — and never visual.

## Reaching other counties, and drawing the grid

Two gaps a reader hit immediately. A county page had no way to reach another
county — you went back to a 323-row index and found it. And the map titled
"interactive infrastructure map" covered one Arizona valley: 175 substations,
because they came from the Postgres stack, which reads two counties.

- [x] Region picker on every region page: a select reaching all 323, plus a
      server-rendered peer row of the counties in the same state.
- [x] National grid layer — 48,132 substations at 69 kV+ and 17,193 generating
      plants, fetched into the Postgres-free observatory pipeline.
- [x] Layers load on demand: 65,325 points is not something to make every
      reader download to look at data centres.
- [x] `make poll-grid`, `--skip-grid`, docs and limitations updated.

### What the measurements decided

Nothing here was sized by guess. The voltage threshold, the tile size and the
decision to fetch rather than inline all came from a number taken first.

- An anchored voltage regex returned 25,082 substations; the corrected one
  returns 48,132. 15,069 are tagged exactly 69.0 kV — the most common value in
  the set, and the one the first version discarded in silence.
- `power=generator` is 22,854 elements in Virginia alone: single turbines and
  panel roofs. `power=plant` is the facility, and only that is collected.
- Inlining 323 region options into 324 pages would have cost ~16 KB each;
  fetching the published regions.json costs one cached request. The peer row
  alone took county-51107 from 91 KB to 96 KB.
- The grid GeoJSON is 11 MB raw, 1.3 MB gzipped. Committing it looked like it
  would double the repository; after `git gc` the whole of `.git` is 6.5 MB,
  because this data packs about eight to one.

### Still open

- [ ] Grid coverage is OpenStreetMap's, so a substation whose mapper left the
      voltage tag blank is absent entirely, and that absence tracks mapping
      effort rather than what is built.
- [ ] Proximity is not connection. Nothing here shows that a facility beside a
      500 kV substation has contracted anything from it.
- [ ] The map layers are verified by test and by reading rendered HTML, never
      by looking at them. No session so far has had a browser connected, so
      nothing in the suite would catch a CSS break or a map that fails to
      paint on a phone.

### Making the grid answer something

The grid shipped as a map layer and nothing else read it. Every region page
could say how many data centres were in a county and nothing about whether the
county could carry another.

- [x] `assign_grid_regions.py` — 65,325 assets summarised into county and state
      totals offline, against the same Census boundaries the facilities use.
- [x] Region pages carry substation count, bulk count, highest voltage and
      generating capacity.

The 230 kV split is the whole point. A raw count ranks a county with forty
69 kV yards above one with a single 500 kV substation, which is backwards for a
load measured in hundreds of megawatts. Loudoun is 64 of 67 substations at
230 kV or above with 500 kV present, against 33% bulk across Virginia — the
densest data-centre county in the world sits on an almost entirely
bulk-transmission grid. That fell out of joining the two datasets rather than
being asserted.

Unknowns are carried, not folded in: a plant with no capacity tag is counted
separately rather than summed as zero, and the 2,898 assets falling in no US
county are dropped rather than attached to the nearest one, which would invent
grid capacity in a real place.

## The footprint that was not a footprint

Every megawatt on the site was allocated by "footprint", and `footprint_m2`
turned out to be three different physical quantities added together: a building
floor plate, a campus land parcel, and a construction site. Pooling them and
dividing LBNL's national total across the result is what produced the ranking.

Measured against the cached snapshot, before any change:

| class | elements | area | share of national MW |
|---|---|---|---|
| building | 1,525 | 20.3 km² | **17.6%** |
| site parcel, no building tag | 174 | 72.3 km² | 62.7% |
| under construction | 29 | 22.7 km² | 19.7% |
| node, no area | 125 | 0 | 0% |

So 82% of a *measured 2024 consumption* figure was allocated to polygons that
are not buildings, and a fifth of it to sites that are not built. A single
3.1 km² parcel in Racine County drew 598 MW — more than half a gigawatt to one
land boundary — while all 239 mapped buildings in Loudoun together drew 1,020.

- [x] Retain the class in `facilities.csv` as `site_class`; it was being
      discarded at fetch time, which is why nothing downstream could tell a
      floor plate from a land parcel.
- [x] Allocate only across operating buildings. A parcel and a construction site
      keep their measured area and get no megawatt figure at all — unknown, not
      zero, the same treatment plants without a capacity tag already get.
- [x] Carry the distinction onto the region pages, methodology and limitations.

`building=no` is an explicit "this is not a building" and must not be read as
one — the 2 km² Meta Los Lunas parcel carries it, and treating it as a building
put Valencia County, New Mexico second in the nation on six elements.

### What changed, measured

| region | before | after | independent figure |
|---|---|---|---|
| Loudoun County, VA | 1,020 MW | **3,034 MW** | — |
| Virginia | 2,255 MW | **4,972 MW** | ~4,100 MW for N. Virginia alone (JLARC) |
| Racine County, WI | 1,028 MW from 5 elements | **30 MW from 2 buildings** | — |
| Maricopa County, AZ | 1,635 MW | 1,050 MW | — |

The old model ranked Maricopa County above Loudoun, which no industry source
agrees with. The corrected Virginia figure is consistent with a measurement the
model never saw; the old one was off by about half, which the methodology page
had already flagged as the weakest link without knowing the cause.

Allocation still sums to 21,918 MW exactly — conservation is unaffected, because
the denominator changed but the total did not. Re-running the pipeline still
produces no CSV diff.

The correction is not a claim of accuracy. Discarded parcels are real facilities
whose load is now carried by buildings elsewhere, so regions mapped campus-first
are understated, and each of them says so on its own page. This trades a large
invisible error for a smaller stated one.

### Still open after this

- [ ] A campus mapped only as a land parcel contributes nothing to its county.
      Estimating it would need a floor-area-to-parcel ratio, which is a
      coefficient this project has no measured basis for and will not invent.
- [x] 45 sites are mapped as under construction. That is a genuine forward
      signal — where capacity is being built — and until `/construction` it was
      measured, counted and then ignored. The page states the signal's limits:
      contributor-reported status, a date that is when the record appeared in
      map history rather than when construction began, and no entry into the
      operating-load allocation.
- [ ] Still nobody has *looked* at any of these pages. No session so far has had
      the browser extension connected.

## Review — the primary rail, and what reviewing it exposed

Measured with CDP device-metrics emulation across ten widths and both themes,
not assessed from a screenshot. Every claim below has a number behind it.

### The rail itself

- [x] **Nothing was ever marked current.** `.nav a[aria-current="page"]` had a
      rule in `globals.css` and no element ever matched it: nothing computed the
      active link, and `trailingSlash: true` would have defeated a raw
      comparison anyway (`/growth/` vs the href `/growth`). Thirteen links looked
      identical on all fifteen routes. Fixed by a `SiteNav` client component with
      `normalisePath`; `/regions/county-51107/` now marks Regions as the section
      with a weaker signal, and does not claim it as the page.
- [x] **The group labels existed only for screen readers.** Three `aria-label`s
      on three `<ul>`s. The reason for grouping thirteen links — two different
      datasets and the reference material for both — was invisible on screen.
      They are printed now, above each bank, as an instrument's plate labels.
- [x] **`--pp-header-h` was a frozen constant against a variable header.** 106px
      declared; the real header ranged 106–190px as the rail wrapped to four
      rows. The recorder's sticky margin plates slid up underneath it. Height is
      now `--header-h` in `globals.css`, both tiers are fixed, and the rail
      collapses to a disclosure before it can wrap. Measured 105px expanded and
      57px collapsed, exactly as declared, at every width tested.
- [x] **21px hit targets**, below WCAG 2.2 SC 2.5.8's 24×24 floor. Now 26px on
      the rail and 40px in the collapsed panel; every focusable element in the
      header clears the floor.
- [x] **Four ragged rows and 190px of sticky header on a phone** — a fifth of the
      viewport spent before the page began. Now a 57px bar and an absolutely
      positioned panel, so opening it cannot change the header's height.
      Escape closes it, navigation closes it, and it carries `aria-expanded` and
      `aria-controls`.

### What the second pass found beyond the rail

- [x] **The ivory palette was rendering on the recorder's paper.** `--accent` on
      eight body links, twenty-eight footer links and the skip link;
      `--ink-muted` on seventeen footer elements; `--ink-1` inherited from `body`
      by every unnamed element in the shared header. Closed at the cause rather
      than per component: `:where()`-scoped catch-alls for links, and
      `color: var(--pp-ink)` on the recorder body so inherited text starts from
      paper ink. A fourteen-token sweep across desktop, collapsed and open, in
      both themes, is clean.
- [x] **The focus ring failed WCAG in dark mode on every route.** It was drawn in
      `--accent-solid`, which the palette defines as "the fill to put white text
      on" — as a ring against the ground it measured **2.15:1 on the page and
      1.98:1 on a panel**, against the 3:1 that SC 1.4.11 and 2.4.13 owe a focus
      indicator. Now `--accent` (the mark colour, 5.07–6.72:1 across every ground
      in both themes), and `--pen-2` on the recorder, which is what that page's
      own chart and buttons already focus in. Five pairs added to
      `audit_contrast.py` so it cannot regress.
- [x] **A green "live" dot beside a static-snapshot date.** The freshness dot took
      `--good` onto the plate: a fourth hue encoding nothing, reading as a health
      light on a page whose banner says the export is point-in-time. Now muted
      paper ink — decoration beside a date that already states the case.
- [x] **`--header-h` was 1px out at both breakpoints** (104/58 declared against
      105/57 measured), because the sum omitted the header's bottom rule.
      Corrected, and `headerHeight.test.ts` now re-adds the declared row heights
      from the stylesheet text and fails if anyone changes one without the sum.
      Mutation-tested both ways.

### Gate

`make lint`, `make typecheck`, `make test-unit` (234 passed), `make
audit-contrast` (every pair clears its floor), `npm run typecheck`, `npm run
lint`, `npx vitest run` (73 passed across 14 files), `npm run build` (352 pages).
Homepage 75 kB gzipped, stylesheet 18 kB gzipped. The fourteen ivory routes were
re-measured at both widths: same heights, same collapse, correct current and
section marks, and no paper token defined on any of them.

## One world across the whole site

The front page had been redesigned into the recorder world and the other fourteen
routes were left on the inherited ivory system. Documented as deliberate; in use
it read as two half-finished sites, and the ivory routes were built from the
exact page structures the recorder world's own brief had refused.

Rolled the world out rather than patching either side.

### What was measured before deciding

| Finding | Value |
|---|---|
| Body copy line length across the site | **148–229 characters** (floor is 65–75) |
| Prose column on `/methodology`, `/understand`, `/sources` | 880px pinned to the **left** of a 1400px page |
| Numeric column headings | Rendered in the reading face, sentence case, because `.table .num` outranked `.table th` |
| Sortable column headings | `text-transform` lost — `font: inherit` does not carry it, and a `<button>` defaults to `none` |
| Table on a 390px screen | Did not scroll; compressed. "LBNL 2024 Report" got 61px, wrapped to four lines, every row stood 74px tall |
| Ivory values surviving in the built CSS after the change | **0** |

### The architecture

One token layer change, then targeted form work. `globals.css` is eighteen
hundred lines of *structure* addressing tokens, so retargeting `:root` moved the
whole site onto chart paper in a single edit, and the rest of the work was
changing what a handful of classes mean rather than where they are used. The
markup barely moved: five `.eyebrow` deletions and two chart wrappers.

`recorder.css` lost its token block and its 40 `body:has(.recorder)` chrome
overrides — those are the site's own header and footer now, merged into
`globals.css` one rule per selector. It kept only what is about a plotted sheet.

### Fixed

- [x] Cards as page structure → neatlined sheets. Tile rows → parameter strips.
      Eyebrows deleted. Badges → stamps. `border-left: 3px` notice → a ruled
      caution. Card grid → index rows. Boxed confidence bands → a reading in the
      measurement face under a rule carrying its step.
- [x] `--measure: 72ch`, enforced on the text and not on the container, so one
      page can hold a full-width table and a readable paragraph. Prose containers
      centred and sized so a section rule ends with the column it opens.
- [x] Links are ink with a hairline underline. Sorted column and current nav page
      now carry the same pen-1 rule — one mark for "this is the reading being
      drawn".
- [x] Charts adopt pen 1 at 1.6px with mono axis labels, so the ink a reader
      learns on the front page means the same thing on `/growth` and `/analytics`.
- [x] Perforated roll edges moved to `.shell`: one continuous roll, not one page
      that looks like an instrument and fourteen that do not.
- [x] Scroll floors on tables and plots, because a column has a width below which
      it stops being a column.
- [x] A five-step stamp-edge ramp re-solved for the new ground: monotonic,
      3.19 → 9.29:1 in both themes. Fraunces dropped — 70 KB of font rendering
      nothing.

### Gate

`make audit-contrast` (every pair clears its floor, both themes), `make lint`,
`make typecheck`, `npm run typecheck`, `npm run lint`, `npx vitest run` (73
across 14 files), `npm run build` (352 pages). Impeccable's design detector
returns clean on the changed files. Home page 75 KB gzipped, two font files
instead of three. Header geometry re-verified across ten widths; the collapsed
nav still opens, traps nothing, and closes on Escape.

## The maps were left behind by the roll-out

Reported as "the map of US has disappeared". It had not: it was rendering, in the
palette the rest of the site had stopped using.

### What the report actually was

The three map components each carried their own copy of the ivory palette as
literals — and `InfrastructureMap.tsx` said so in a comment: *"These mirror
--seq-1..7 in globals.css but are declared here as literals."* The reason is
real (MapLibre paint expressions take resolved colours, and a custom property
holding `light-dark()` does not resolve through `getComputedStyle`), but moving
the stylesheet onto chart paper left all three copies behind:

- every facility kept `--caution` amber, a hue that now grades nothing
- every mark's halo painted the retired `#faf8f3` as a near-white ring on sage
- substations and plants kept the old accent and status greens
- the nine-step stage choropleth kept a ramp mixed for a page that no longer
  exists
- the CARTO basemap sat in the page as a near-white rectangle

### Fixed at the class, not the instance

`lib/mapPalette.ts` holds one copy. `mapPalette.test.ts` parses `globals.css` and
fails if any value stops matching its token, and additionally asserts the ramp is
monotonic, that dark is the exact reverse of light, and that every mark clears
3:1 against the paper it is drawn on. 10 tests.

- [x] Data centres take pen 1, substations pen 2, plants pen 3 — the same fixed
      assignment as every other surface, so the ink a reader learns on the front
      page means the same thing on a map.
- [x] Basemap made translucent over the paper rather than tinted toward it.
      Tinting first produced grey land inside a sage page; letting the sheet show
      through is the truthful version of the same idea.
- [x] MapLibre's control chrome re-skinned as a ruled plate. Every selector is
      prefixed `.map-container` because MapLibre's stylesheet is imported by the
      component and lands after `globals.css` — at equal specificity its white
      rounded card won, on a smoked drum.

### Two things worth recording about the investigation

The first screenshots showed a blank map, then a map filling only the left third.
Both were my harness: headless Chrome runs with `--disable-gpu`, so `webgl2` was
false, and under software rendering the tiles need ~25 s. Relaunching with
SwiftShader and waiting properly showed a complete, correct map. A worktree build
of HEAD confirmed `.map-container` was byte-identical and neither map component
had been touched — the geometry was never the bug.

### Gate

`make audit-contrast` green in both themes, `npm run typecheck`, `npm run lint`,
`npx vitest run` (83 across 15 files), `npm run build`, Impeccable's detector
clean on `src`. A sweep for all 25 retired palette literals across every `.ts`,
`.tsx` and `.css` in `src` returns one hit, inside a comment describing the bug.

## The country on the front page was a lattice, not a map

The reported symptom was "the US map has disappeared". It had not disappeared and
it was not the MapLibre work: the front page's plot sheet is a server-rendered
SVG that draws the country out of 64,848 substations and power plants, and three
faults were stacked on it.

- [x] `binToGrid` threw the count away. It returned one mark per occupied cell
      and de-duplicated the rest, so 3,922 cells drew 3,922 identical dashes on a
      nine-unit pitch. That is a regular mesh whose only shape is its outer edge —
      not a country. It now returns `[x, y, count]` and the mark is weighted by
      how much grid is in the cell, which is what makes the eastern seaboard, the
      Ohio valley and the California coast appear. The counts run 1–278 with a
      median of 9, so the scale is logarithmic; linear puts nine cells in ten at
      the lightest weight and gives the lattice straight back.
- [x] The sheet was ruled behind the drawing. `.pp-wide-body` paints chart paper
      at a 9px minor pitch and the stipple sits on a 9-unit pitch that renders at
      10.6px. Two grids one pixel apart in frequency do not layer, they interfere,
      and the map read as a printing artefact. The map's plate gives up its
      ruling; it keeps the perforation and the neatline.
- [x] Facilities were drawn in pen 2. Every other map on the site had just moved
      to pen 1, so the single surface where facilities and grid appear together
      was the one surface where a data centre was not the colour the reader had
      learned two screens earlier. Now pen 1, and the legend swatches follow
      because they share the class.

Three smaller faults the fix exposed:

- [x] The underlay's heaviest cells drew as heavily as a large data centre —
      context outweighing subject. Ceiling lowered.
- [x] A facility with no power figure was drawn in `--pp-ink-muted`, the
      underlay's own ink, so it read as a substation. It takes
      `--unmeasured-edge` now, which is the token the rest of the site already
      uses for exactly this.
- [x] The Puerto Rico inset had no fill, so mainland marks showed through it and
      Louisiana substations appeared inside the box. Setting `fill` on the
      element did nothing: a presentation attribute loses to any class rule, and
      `.pp-map-neatline` declared `fill: none`. Same specificity trap as
      `.table .num` over `.table th`. Fixed at the class.
- [x] On a phone the sheet gave a quarter of its width to card padding. The
      drawing takes the full plate below 900px; only the vertical padding stays.

### Guard

`binToGrid` now has two tests it did not have: one asserting the per-cell counts,
one asserting the counts sum to the number of points, so binning cannot silently
drop an asset. The first is the one that bites — the old behaviour passes every
test that only checks how many cells came back.

### Gate

`make audit-contrast` green in both themes, `npm run typecheck`, `npm run lint`,
`npx vitest run` (85 across 15 files), `npm run build`. Verified at 1440 and 390
in both themes, plus a 3× zoom on the inset corner.

## Site-wide review: what a measurement pass found that screenshots did not

Ran a probe over 16 routes × 2 widths × 2 themes, checking target sizes, contrast
against composited backgrounds, heading order, duplicate ids, accessible names,
landmarks, keyboard reach into scroll containers, and text overflow. Then read
every finding in source before touching anything, which is what separated the
five real defects from the two false positives.

### The one that was not a visual defect at all

- [x] **127 of 323 regions printed a zero that was false or unknown.** The
      footprint and megawatt columns ran `toFixed(2)` and `Math.round` over three
      situations that mean three different things. 53 regions hold only points
      and campus boundaries — no building, so no floor plate was measured and
      there is nothing to take a share of the national total; those showed
      `0.00 km²` and `0 MW`. 74 more have a real footprint under 5,000 m² that
      rounds away, and 15 a real allocation under half a megawatt. This is the
      site's own cardinal rule broken in its widest table, and it was invisible
      to every screenshot because a zero looks like data.

      `formatRegionFootprintKm2` / `formatRegionMw` now render an em dash for
      unmeasured and `<0.01` / `<1` for small-but-real, so the two can never
      print the same string. Applied to the table, the region page's four
      metrics, and the region page's meta description — a search result was the
      one place "0 MW" travelled without its column heading to qualify it.
      Four tests, including one that asserts a small measurement and an absent
      one do not render alike.

### WCAG 2.2 SC 2.5.8, four failures

- [x] Column sort buttons were 15px tall. They now claim the header cell's own
      padding box. The active-column mark moved from an inset box-shadow to an
      underline, because a shadow sits at the bottom of the button and would have
      drifted eight pixels the moment the control grew a hit area.
- [x] Homepage region links were 14px. Padding grows the link's box and the row
      grows with it — pulling the height back with a negative margin measures 24
      and hits 14, because `.pp-stack-name` clips its overflow for the ellipsis
      and hit testing follows the clip.
- [x] Footer links: 14px tall on a **23.5px** pitch. The spacing exception needs
      24, so this failed by half a pixel.
- [x] `<summary>` disclosures were 19.7px.

### WCAG 2.1.1, keyboard

- [x] Nine scroll containers were mouse-only. Two of them hold a single `<svg>`
      and nothing focusable, so a keyboard user could not reach the right-hand
      half of the plot at all. New `ScrollArea` puts them in the tab order with
      `role="region"` and a name, and they get a focus ring drawn inside the box.
      Proved with a real Tab walk: 23 tabs to the regions table, `:focus-visible`
      matching, ring measured.

### MapLibre chrome, again, in two more places

- [x] The attribution was still a white pill with black text in dark mode.
      MapLibre writes its base rule as `.maplibregl-ctrl.maplibregl-ctrl-attrib`
      and its collapsed state as `.maplibregl-ctrl-attrib.maplibregl-compact` —
      two classes each, both later in the bundle — so the single-class override
      tied and lost. Same defect as the control group, one selector deeper.
- [x] **Every popup on the site was still MapLibre's white card.** Those rules
      were never prefixed at all. Also only four of the eight tip anchors were
      covered, and MapLibre picks a diagonal anchor whenever a mark is near an
      edge, which on a national map is most of them.

### Two findings that were not defects

The search input reads as unnamed to a naive probe and has a proper wrapping
`<label>` with `.sr-only` text. The map attribution measured 2.5:1 because the
probe read `color(srgb 0.83 …)` as 0-255; composited properly it is 5.7:1 light
and 7.5:1 dark. Both were checked in source before anything was changed.

### Gate

`npm run typecheck`, `npm run lint`, `npx vitest run` (89 across 15 files),
`npm run build`, `make audit-contrast` green in both themes, and the probe
re-run: zero contrast failures, zero overflow, zero heading jumps, all five
scroll containers keyboard-reachable. The remaining small-target entries are
inline links inside sentences, which SC 2.5.8 exempts.

## The plot sheet still had no US map, and why the third attempt was different

The first two attempts tuned the marks. The third stopped and asked what the
marks could possibly be asked to do.

### The finding

**A density field cannot draw a country.** The sheet had no coastline by design —
the stated idea was that the shape would emerge from 65,325 substations and
power plants, so every mark on the plate would be a record rather than
decoration. It does not emerge. The grid follows population, and there is
nothing in Nevada to stipple, so Nevada had no edge. No weighting curve, cell
size or opacity ramp was going to produce one, because the shape of a country
is not a thing that was measured.

- [x] Dissolve the committed county boundaries into a contiguous-state coastline
      and draw it in the paper's own hairline, never in a pen. It is reference
      geography, and the sheet now says so in its copy: the coastline is the one
      thing on the plate that was not measured.
- [x] Source it from `data/reference/counties.geojson`, the same file that
      decides which county every facility belongs to, so the shape a reader
      recognises and the shape the data was assigned against cannot drift.
- [x] Fit the sheet's extent to the land instead of to the grid. Fitting to the
      data meant a new substation in Maine could move every facility on the
      sheet.

Edge de-duplication is the obvious way to dissolve a clean topology and it does
not work here: the county file was generalised server-side per feature, so
adjacent counties do not share vertices and 78,016 interior segments look like
coastline. `unary_union` after `buffer(0)` heals it in one line.

### The lattice, and the thing that made it visible

- [x] The grid layer was binned to a nine-unit cell and read as a halftone
      screen printed over the map. The cause is occupancy, not weighting: a
      lattice is invisible while sparsely filled and unmistakable once it is
      not, and at nine units the populated half of the country had something in
      nearly every cell. At four units the same assets occupy 30% and the
      quantisation stops being a pattern the eye can find.
- [x] 17,500 interior rings in the dissolved outline, every one a sliver where
      two counties disagree about a shared border. The largest traces 110 km of
      the Kansas–Nebraska line at 2 km wide — too big for an area threshold, and
      it drew as a stray dash across Kansas. Counties tile their states, water
      included, so a hole in the union can never be a lake. All interiors are
      dropped, and the docstring says why rather than tuning a number.

### A truth defect found while looking at a visual one

**2,898 of the 65,325 grid assets are not in the United States.** The Overpass
boxes reach into Sonora, Chihuahua, Ontario and the Gulf. The per-county totals
were always right because they are keyed on the county assignment — but
`assign_grid_regions.py` computed that assignment, used it, and threw it away,
so the two surfaces that read the raw rows published it unfiltered: the map drew
Mexican substations on a plate captioned "the contiguous states", and the front
page counted them in a national total.

- [x] `assign_grid_regions.py` writes the assignment back to `grid.csv`, the way
      the facility snapshot already carries `county_fips` and `state`.
- [x] `build_grid` and the meta counts publish only assigned rows. 65,325 →
      62,427. A test asserts an unassigned row is not published.

### Weight

Adding a coastline and tripling the grid marks should have cost 45 KB gzipped.
It ended up 9 KB *lighter* than before either change, because the encoding was
the larger win: sorting the marks row-major took the grid layer from 35 KB
gzipped to 30, and writing the gap to the previous mark instead of its position
took it to 10. The page is 426 KB raw / **72 KB gzipped**, down from 520 / 124.

### Gate

`npm run typecheck`, `npm run lint`, `npx vitest run` (92 across 15 files),
`npm run build`, `make lint`, `make test` (299 passed), `make audit-contrast`
green in both themes. `build_basemap.py`, `assign_grid_regions.py` and
`build_site_data.py` re-run byte-identical, so a `git diff` still means real
movement. Verified visually at 1440 light, 1440 dark and 390 phone.

**Not re-run:** the 16-route browser probe. I killed the long-lived headless
Chrome with a `pkill` and it will not stay alive in this sandbox. Structure was
checked instead on the built HTML for five routes (one `h1`, one `main`, no
heading jumps, no duplicate ids, no unnamed `svg[role=img]`); target sizes and
composited contrast were not re-measured.

---

# Fix plan for the staff review

Fifteen findings, grouped into five commits. Order matters: the pipeline guard
(A) is what makes the UI guards (B) unreachable rather than merely quiet, and
the national-region fix (C) depends on nothing.

## A. The pipeline stops publishing a grid layer it did not build

The headline finding. `fetch_grid.py` writes `county_fips`/`state` blank,
`assign_grid_regions.py` is the only stage that fills them, and it sits in
`poll.py`'s tolerated-failure set — so a failed assignment publishes
`grid.geojson` with zero features, `substation_count: 0`, and exit code 0.
Proved with a fixture: blanking the column on all 65,325 rows produced a 0-byte
layer and a successful run.

- [x] `build_site_data.py`: after the existing `facilities and regions` guard,
      refuse to publish when `grid` has rows and none carries a `county_fips`.
      One choke point, all three surfaces (`grid.geojson`, `substation_count`,
      `plant_count`) route through it.
- [x] `poll.py`: hoist the tolerated set to a module constant and return
      `1 if any(s not in TOLERATED for s in failed) else 0`. Today only
      `assign_regions.py` can fail the run — `build_site_data.py`,
      `allocate_power.py`, `build_basemap.py` and `fetch_osm_snapshot.py` all
      exit 0 on failure. With the guard above, a failed grid assignment now
      surfaces as a failed `build_site_data.py`, which is not tolerated.
- [x] `poll.py` docstring: the stage list has `assign_grid_regions` before
      `fetch_osm_history`/`assign_regions`; the code runs it after.
- [x] Test: an unassigned `grid.csv` raises rather than publishing zeros.
      Mutation check — remove the guard and the test must fail.

## B. The front page stops asserting numbers it cannot support

- [x] `page.tsx:529` — `(meta.substation_count ?? 0) + (meta.plant_count ?? 0)`
      renders "0 substations and power plants" when the layer is missing. Take
      the `hasGrid` shape already in `observatory-map/page.tsx:34-40`, which
      carries a comment naming this exact risk, and drop the clause when there
      is no grid rather than printing a zero.
- [x] `page.tsx:628` — hardcoded "All 1,853 facilities". The only number on
      that page not read from `meta`. → `meta.facility_count`.
- [x] `page.tsx:155` — `scenarioAt(year, "low") ?? 0` draws a fabricated zero
      for any projection year missing a low or high scenario. Filter
      `projectionYears` to years carrying both, rather than defaulting. Latent
      today; reachable by adding a reference-only row to `national_energy.csv`.
- [x] `PlotSheet.tsx:247` — the aria-label claims 1,853 total and its parts sum
      to 1,851. It mixes `facilities.length` (all) with `buildings`/`others`
      (mainland only). Count the label from the same set it describes.
- [x] `PlotSheet.tsx:102` — facilities are split `PR`/not-`PR` while the grid is
      bounds-filtered to CONUS, so an AK or HI facility would be clipped off the
      sheet and still counted in its label. Filter both against the same box.
- [x] `methodology/page.tsx:108` — "moves Loudoun County to 3,034 MW and
      Virginia to 4,972 MW", present tense, hardcoded. Exact against
      `regions.json` today, which is why nobody will notice when it stops. Read
      the two figures, or name their vintage.

## C. `/regions/national-US/` uses the national figures it already has

Every metric-sub branches on `region?.building_count === 0`, and `region` is
`undefined` on the national page, so the built HTML says "km² across **0
buildings**" and leaves three metrics as uncaptioned dashes — while
`meta.json` carries all of it.

- [x] Synthesise the national row by summing the `kind === "state"` rows the
      page already loads. Verified to reconcile exactly: 1,853 facilities,
      1,506 buildings, 21,918 MW, 47.7 M gal/day — the same figures as
      `meta.json`. Every existing branch then works unchanged, including the
      `region!.site_area_m2!` assertions at line 260.
- [x] Keep `isNational` for the label branches (`subtitle`, `currentLabel`,
      `peerLabel`) so the page still reads "National" and not "State".
- [x] Do **not** publish the row into `regions.json` — it would surface in the
      regions table and the picker, which is a product decision, not this fix.

## D. Smaller ones

- [x] `changes/page.tsx:43` claims "The 500 most recent times"; line 106 renders
      `slice(0, 200)`. 200 rows verified in the built HTML.
- [x] `RecorderChart.tsx:191` — `role="img"` plus `tabIndex={0}` plus an
      aria-label instructing arrow keys the widget cannot receive in browse
      mode. Either make it a real `application`/listbox-style widget or drop the
      instruction; the lazy correct answer is to drop it.
- [x] `NationalEnergyTable.tsx:61` assumes CSV row order (`historical[0]`) where
      `page.tsx:129` sorts explicitly for the same value, and prints a year
      range under a dash.
- [x] `ObservatoryMap.tsx:131` latches `requested.current` before the fetch, so
      a failed grid fetch never retries — toggling the layer leaves "grid layer
      unavailable" until reload. Reset it on failure.
- [x] `sitemap.ts` lists `/sites`, `/map` and `/analytics` unconditionally while
      `sites/[siteId]` is guarded on the Arizona snapshot being present.

## E. Needs a decision, not a fix

- [ ] `state:AK` and `state:HI` grid summaries are computed into
      `grid_regions.csv` and reach no page, because `build_site_data.py:240`
      left-joins grid onto *facility* regions. Publishing them means region rows
      with `facility_count: 0`, which changes what the regions table and picker
      are for. Raised earlier and never answered — not started.

## Gate

From the repo root, per commit:

    make lint
    .venv/bin/python -m pytest -m "unit or contract"    # 234 today
    npm --prefix apps/web run typecheck
    npm --prefix apps/web test                          # 92 across 15 files
    npm --prefix apps/web run build                     # 351 routes
    make audit-contrast

Plus, for A: re-run `build_site_data.py` and confirm it is byte-identical, so
`git diff data/observatory` still means real movement; and replay the blanked-
`county_fips` fixture to confirm the guard now fires where it previously
published zeros. For C: grep the built `regions/national-US/index.html` for
"0 buildings" — it must be gone, and the three dashes must be real figures.

Push once, at the end. `pages.yml` deploys `main` on push.

### What landed

One commit rather than five: the seven defects are one review, and splitting a
guard from the surface it protects would put half the fix in each half of the
history.

The pipeline gate is the part worth recording. Replaying the original fixture —
`grid.csv` complete, every `county_fips` blanked — used to produce a 0-byte
`grid.geojson`, a published `substation_count` of 0 and exit code 0. It now
stops:

    GUARD FIRED: grid.csv has 65325 rows and not one carries a county.

`poll.py`'s exit code was mutation-checked rather than asserted: with
`build_site_data.py` failing it returns 1, and adding that script to
`TOLERATED_FAILURES` in a live interpreter flips the same run to 0, so the
return value genuinely consults the set.

The national page now reads `20.00 km² across 1,506 buildings`, `21,918 MW` and
`47.67 million gal/day`, which reconciles with `meta.json` to the metre. The
plot sheet's description sums: 1,506 + 347 = 1,853.

The projection band was checked by putting a reference-only 2035 row into the
published payload and rebuilding: the band ends at 2030 with three forward
points instead of reaching 2035 at zero. The row was then reverted.

Gate: `make lint` clean, `make test` 306 passed / 138 skipped (the skips are the
Postgres integration tests; local Homebrew pg on 5432 has no `helios` role),
`npm run typecheck` clean, 95 vitest across 15 files, `npm run build` 350 routes,
`make audit-contrast` all pairs clear. `build_site_data.py` re-runs
byte-identical, so `git diff data/observatory` still means real movement.

**Correction to the gate in the plan above:** `pytest -m "unit or contract"`
does not cover `tests/unit/test_observatory_pipeline.py` — that file carries no
marker, so the marker-filtered run silently deselects all 72 of its tests,
including the new ones. `make test` is the command that runs them.

### Still open

- The front page quotes 62,427 grid assets in prose and the plate below it draws
  61,983. Both are honest — the plate is cut to the contiguous box — but they sit
  a paragraph apart and nothing explains the gap. Raised before, not fixed here.

## Closing the front page's two grid counts

Fixed the item above. The gap was never in the numbers — both are derived and
both were right — it was that the page put a national figure directly above a
contiguous drawing and left the reader to guess which was wrong.

Three things changed, one of them not on the original ticket. The prose labels
its figure national. The paragraph explaining the contiguous cut now says the
cut applies to the grid too, and stops implying Puerto Rico is exempt from it:
the inset carries PR's two facilities and not its 115 grid assets, which the
old wording read as covering. And `PlotSheet.tsx`'s docstring claimed 358
assets off the paper "past 165° west" — stale (444 today) and never an accurate
description of a four-sided box, which is what actually puts Puerto Rico
outside it.

The measured split, from `grid.csv`: 62,427 assigned nationally, 61,983 inside
the box, 444 out — HI 211, AK 118, PR 115.

The test asserts the off-sheet set is exactly {AK, HI, PR} rather than
reconciling the counts, because reconciling them is arithmetic on one
function's own output and passes whatever the data says. It duplicates the
CONUS box deliberately: the box is the assertion under test, so a copy that
has to be edited in step is the point. Mutation-checked by moving `lon_min`
from -125 to -120, which turns the three states into six and fails it.

Gate: `make lint` clean, `make test` 307 passed / 138 skipped (the skips are
the Postgres integration tests — local Homebrew pg on 5432 has no `helios`
role), `npm run typecheck` clean, 95 vitest across 15 files, `npm run build`
clean, `make audit-contrast` all pairs clear. The built `index.html` was read
back: prose reads "62,427 nationally", the sheet's own description reads
"61,983 substations and power plants". No data file changed, so the rebuild
diff gate is untouched.

### Still open

- Nothing carried over from the item above.
