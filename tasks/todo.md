# Redesign the UI/UX along the lines of the Affordability Index

Direction set by the user: review `Tech-affordability-index` (published as
`varad-more/affordability-index`), take its design language, and apply it here.
Ivory default with a dark toggle; assertion class re-encoded as an ordinal ramp
plus a border treatment. Repo rename deferred; the US-scope data expansion is a
separate program.

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
