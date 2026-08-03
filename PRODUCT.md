# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Weighted, in this order:

1. **Recruiters and hiring managers** arriving from a CV or GitHub link with roughly
   ninety seconds. They are not here for county-level megawatts; they are deciding
   whether the person who built this can build and reason. The homepage has to
   carry that verdict on its own.
2. **Energy and policy analysts** — grid planners, utility staff, county officials,
   researchers — who need the numbers to be comparable, precise, and traceable.
   They arrive deeper in the site, or scroll past the headline.
3. **Journalists and the informed public**, usually searching for one county, who
   need a figure they can quote without misrepresenting it.

The design resolves conflicts in favour of the recruiter's first impression, but
only ever by making the analyst-grade depth *more* visible — never by simplifying
a figure into something an analyst would call wrong. The depth is the impression.

## Product Purpose

Helios counts US data centres, tracks how that count moves, and estimates the
electricity and water they draw — entirely from public records, with every figure
labelled by what kind of claim it is.

Success is a reader who leaves knowing three things they did not know, and who
could not have been misled by any number they saw on the way.

## Positioning

The mechanism a neighbouring product could not truthfully copy: **every value
carries its assertion class, and the classes are enforced in the pipeline, not
applied as a display convention.** Commercial data-centre trackers publish a
number; Helios publishes a number, the document it came from, and an explicit
statement of how much inference sits between the two.

Two claims are permanently withheld because no public source supports them: when
a facility was built, and that a facility's disappearance from OpenStreetMap
means it was demolished.

## Operating Context

Two datasets share a vocabulary and a website and nothing else:

| | National observatory | Arizona site model |
|---|---|---|
| Question | How many, where, growing how fast | What is being built on *this* parcel, and how sure are we |
| Grain | 1,853 facilities · 323 regions · 45 states + DC + PR | 13 candidate sites, East Valley, Maricopa County |
| Storage | committed CSV → JSON → static site | PostGIS + FastAPI, exported to a static snapshot |
| Database | none | required |

Deployment is GitHub Pages at `us-data-center-observatory.varadmore.me`: a static
Next.js export reading flat JSON. There is no server at runtime. Every page
carries a banner stating the deployment is a point-in-time snapshot and when it
was taken.

CSV is canonical and committed so that `git diff` between two polls *is* the
change log. Writers are byte-stable; CI fails when a derived file stops following
from the CSVs it was built from.

## Capabilities and Constraints

**Assertion classes** — every stored value carries one, passed through the API
unchanged: `reported`, `extracted`, `calculated`, `inferred`, `predicted`,
`unknown`. An `unknown` renders as absent, **never as zero**.

**Facility classes** — only `building` (1,506) carries a power or water figure.
`site` (174, a campus mapped as land), `point` (128, no geometry), and
`construction` (45) are counted and mapped but given no load figure at all. Land
area is not floor area.

**The time axis is a mapping curve, not a construction curve.** 4,309 OSM edit
events, 2015-07-11 to 2026-06-19. The pre-2017 stretch, when the tagging
convention was still being adopted, must be shaded and labelled as unqualified on
every chart that reaches back that far — enforced by a test.

**Power allocation** — LBNL's reported national total (192 TWh / 21,918 MW avg,
2024) split across buildings by floor-area share. The pieces re-sum to the
published figure exactly; a test enforces it. The output is an `inferred` upper
bound, never a meter reading.

**Not estimated on principle**: substation capacity (FERC Form 715 is
CEII-restricted), per-facility metered power or water, build dates, demolitions.

**Technical**: Next.js static export (`output: "export"`, `trailingSlash: true`),
served from a domain root so `basePath` is empty. MapLibre for maps. Charts are
hand-rolled inline SVG with no charting dependency — a deliberate standing choice,
reaffirmed 2026-08-01, to be implemented as a shared primitive layer rather than
one-off components.

## Brand Commitments

- **Name: Helios.** Confirmed to stay, 2026-08-01, despite the repo and domain
  being renamed to `us-data-center-observatory`.
- **Tagline: "US AI Infrastructure Observatory."** Replaced "Open AI
  Infrastructure Observatory" on 2026-08-01 because the eye reads "Open AI" first.
- **Byline: Varad More**, `varadmore.me`, `github.com/varad-more`. The email
  address is deliberately unpublished.
- **Voice**: plain, specific, unhedged about what is known and equally unhedged
  about what is not. Numbers are never dressed up. A caveat is stated once,
  clearly, next to the figure it qualifies — not buried in a footnote and not
  repeated defensively.
- Licence Apache-2.0; OSM data ODbL, attributed.

## Evidence on Hand

Real, committed, and already generated — no figure on this site needs inventing:

- `apps/web/public/data/` — `regions.json` (323 regions with facility counts,
  footprint, est_mw, est_gal_per_day, substation and plant counts, max voltage),
  `series/*.json` (330 monthly series: national, per state, per county),
  `national_energy.json` (LBNL historical + low/reference/high projections to
  2030), `changes.json`, `facilities.geojson` (1,853), `grid.geojson` (62,427
  assets, US only), `basemap.json` (the dissolved contiguous-state coastline),
  `meta.json`.
- `apps/web/public/api/` — the Arizona study: sites, stages, analytics, sources.
- `data/observatory/*.csv` — the canonical source of all of the above.

**Absences future work must not fabricate**: no build dates, no per-facility
meter readings, no substation capacity, no operator attribution without a direct
filing, no commercial directory data. One `reported` facility-scale load figure
exists in total — MPSC docket U-21990, DTE Electric, 1,383 MW, Saline Township MI.

## Product Principles

1. **An inferred value must never render like a reported one, and an unknown is
   never a zero.** This outranks every visual consideration.
2. **A mapping curve must never read as a construction curve.** Where the shape of
   a chart could be misread as growth in the world rather than growth in the
   record, the chart says so on its face.
3. **Every figure traces to its document.** Provenance is a feature of the
   interface, not an appendix.
4. **Gaps stay visible.** Sources that cannot be reached are published alongside
   the ones that can, with the reason. Closing a gap by deleting its disclosure is
   the one forbidden fix.
5. **No infrastructure the project does not need.** No database for the
   observatory, no charting dependency, no Kafka, no Kubernetes.

## Accessibility & Inclusion

WCAG contrast is enforced mechanically: `make audit-contrast` checks every
interface colour pair against its floor and is part of `make check`. Light and
dark themes both ship; theme is applied before first paint. Any new chart colour
must clear the same gate.
