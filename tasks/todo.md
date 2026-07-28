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
