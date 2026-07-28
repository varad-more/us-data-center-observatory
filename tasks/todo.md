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
- [ ] **Register FERC RM26-4 as a planned source.** On 18 June 2026 FERC issued
      show cause orders to all six RTOs/ISOs and directed them to publish
      large-load network upgrade projects and costs on a *searchable platform*,
      plus aggregated large-load requests per transmission zone. Nothing to
      build yet; a registry entry citing the docket makes the gap visible and
      dated, which is what the registry is for.
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

- [ ] `source.notes` renders nowhere, so ADWR's stated deferral reason is held
      and invisible — the same defect just fixed one field over.
- [ ] The interconnection gap is asserted in `limitations.md` twice,
      `methodology.md`, the analytics caveat and two source comments, and the
      registry says nothing. The page built to show gaps omits the biggest one.
- [ ] Two `future-phase` tag values in `registry.py` — last of the phase naming.
- [ ] `ConnectorStatus.DEGRADED` and `DISABLED` are statuses no code can
      produce. Either derive them from `last_success_at` or drop them.
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
