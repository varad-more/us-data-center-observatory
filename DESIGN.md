# Design

<!-- impeccable:design-source apps/web/src/app/recorder.css -->

The whole site runs one visual world, **the recorder**. It began on the home
page under `.recorder` while the other fourteen routes kept an inherited warm
ivory system, and the boundary was documented here as deliberate — two materials
for two arguments. In use it was not read that way: crossing from the front page
to a region page changed paper, typeface and chart language in one click, and
what it communicated was two half-finished sites rather than one considered
distinction.

So the tokens moved from `body:has(.recorder)` to `:root`, and `globals.css`
became this world's stylesheet. `recorder.css` keeps only what is genuinely about
a plotted sheet — the rulings, the pens, the crosshair — and addresses the same
tokens through a small alias block. The ivory palette is gone: no value from it
survives in the built CSS.

## The recorder world

### Why this form

A strip-chart recorder is pre-printed paper advancing under inked pens. It is
the only common instrument whose native grammar already draws the distinction
this project exists to hold: **a flat trace means "measured, nothing happened"
and blank paper means "not measured".** Every KPI tile ever drawn renders both
as `0`.

Three further properties earn their place:

| Property of the instrument | What it carries here |
|---|---|
| Chart speed is printed in the margin | The warning that this records *mapping*, not building, sits where a reader of this instrument already looks for the terms of measurement |
| A pen against its stop | The native picture of an upper bound, which is what every allocated megawatt figure is |
| One pen per channel | `reported`, `observed` and `predicted` each get their own ink without any of them being invented for the occasion |

Seed key `133091bd`. The direction contract is an HTML comment in the built
output; grep `IMPECCABLE DIRECTION CONTRACT` in `apps/web/out/index.html`.

### Ground and ink

Tokens are declared on `:root` in `globals.css`, under the inherited names
(`--page`, `--ink-1`, `--border`…), because eighteen hundred lines of component
CSS already address them and renaming all of it would change nothing a reader
sees. `--pp-*` survives as an alias layer for the two hundred rules in
`recorder.css` that use those names.

| Token | Light — chart paper | Dark — smoked drum |
|---|---|---|
| `--pp-paper` | `#dde3d6` | `#1a1815` |
| `--pp-paper-plate` | `#d4dbcb` | `#211e1a` |
| `--pp-paper-deep` | `#cbd3c1` | `#262320` |
| `--pp-ink` | `#232420` | `#ede7d9` |
| `--pp-ink-2` | `#4e4f45` | `#b5ae9e` |
| `--pp-ink-muted` | `#565850` | `#948e80` |
| `--pen-1` | `#b03a26` | `#de5c39` |
| `--pen-2` | `#4a4ebf` | `#7c7ddd` |
| `--pen-3` | `#0f7a55` | `#2fa277` |

Light is the default because of the use scene: a recruiter on a laptop in a lit
office with ninety seconds, and an analyst at a desk during the working day.
Dark is a *selected* second world — smoked drum paper, rulings as scratches
catching lamplight — not an inverted flip.

**Every value above is gated.** `make audit-contrast` now carries the recorder
pairs alongside the inherited ones, and each pen is checked against every ground
it is actually drawn on. `--pp-ink-muted` was re-stepped from `#5f6157` /
`#8a8477` because it carries every label, tick and caption at 10–12px and so
owes the 4.5 text floor against the *readout panel*, not just against open paper
— it measured 4.09 and 4.20.

The three pens were validated as a categorical set (lightness band, chroma
floor, CVD separation, normal-vision separation, contrast) against each ground
before anything was drawn.

### Rulings

The paper is real CSS, not a texture image: four `repeating-linear-gradient`
layers on `.pp-plot`, minor every 9px and major every 54px, both axes. Margin
plates are *not* ruled — on a real chart the header block is printed over the
ruling, and keeping ruling off prose is what stops the text columns reading as
busy.

`.pp-roll` draws tractor-feed perforations down both edges with a repeating
radial gradient. They run the full length of the page because the constant feed
rate is the entire reason a strip chart can be read as time at all.

### Type

| Face | Role |
|---|---|
| **Archivo** (variable, weight + width) | Margin plates, headings, labels. A grotesque drawn from the American gothics that set newspaper decks and signage. The width axis lets a label plate compress to fit its column rather than wrap. |
| **Azeret Mono** (variable) | Every measured value. Monospace here is measurement notation, not a costume for "technical" — these are instrument readings and they have to align in a column to be compared. |

Both self-hosted through `next/font/local`, SIL Open Font Licence, latin subset.
Fraunces carried the display voice on the fourteen inherited routes and is no
longer loaded — an unused variable font is 70 KB a reader downloads to render
nothing.

Two registers, and the split is the instrument's own. A **plate title** is
silkscreened on the panel: heavy, condensed, upper case, naming the sheet you are
looking at — `h1`, `h2`, and a sheet's `.card-title`. Below that the page is
prose, and prose in tracked caps is unreadable, so `h3` and `h4` stay sentence
case in the same face at a normal width.

Margin lettering is small, tracked `0.13em`, upper case — instrument silkscreen,
which is a real typographic register: every label on a recorder's panel is set
that way because it must survive being read at an angle in bad light.

### Marks

- Traces are `1.6px` with `vector-effect: non-scaling-stroke`, thin enough that
  the printed divisions stay readable underneath.
- **Stepped, never interpolated.** These series change on discrete months; a
  diagonal would draw facilities arriving on dates no edit supports.
- The electricity channel is a `spot` render: squares at published years joined
  by a **dotted** connector, because the pen genuinely lifts between them. A
  solid line would draw values for years LBNL never published, in the same ink
  as the ones it did.
- Scenario ranges are a filled band, because LBNL publishes a range.
- The dead band is **hatched, not greyed** — grey reads as "less", hatching
  reads as "do not read this", which is the actual instruction.
- Allocation bars end in a stop mark standing proud at both ends. A flush end
  reads as a measurement that happened to land there.
- Absence is drawn in `--pp-ink-muted`, never in a pen colour. A facility with
  no power figure is not a low reading.

### Claim stamps

`.pp-stamp` sets the word in `--pp-ink-2` and carries the claim in the border
plus a dot. Setting the label itself in the pen colour put a 9px green word on
green paper at 4.05:1 — under floor, and a violation of the house rule that
colour grades a fact and never states it. Three signals now carry it: the word,
the edge, the dot.

### The one moving part

A multi-channel chart is read by laying a straightedge across every channel at
once. So the crosshair spans all three and `.pp-readout` in the margin is slaved
to it — the panel has no value of its own, only the value under the cursor. It
rests at the last recorded month; resting at the right-hand end of the paper
showed three lines of "no paper", which is correct and a terrible first
impression.

Keyboard: focus the chart, `←`/`→` step a month, `Shift` a year.

Everything else on the page is paper. Transitions are limited to
`background-color` and `box-shadow`; animating a layout property was caught by
the detector and removed.

### Refused

Cards as page structure (neatlined sheets instead), the hero-metric tile row,
eyebrows above headings, section numbers, gradient text, glass, sparklines
standing in for content, and any second y-axis. **Never a dual-axis chart** —
that is what a shared time base with stacked channels exists to replace.

## The maps

`apps/web/src/lib/mapPalette.ts`, imported by all three map components.

MapLibre paint expressions take resolved colour values, and a custom property
holding `light-dark()` does not resolve through `getComputedStyle`, so the map
palette cannot read the stylesheet at runtime. It has to be literals — and that
duplication failed silently the first time the stylesheet moved. All three map
components carried their own copy of the ivory palette, so after the roll-out
every facility kept its `--caution` amber, every mark's halo kept painting the
retired page colour as a near-white ring on a green-grey ground, and the
nine-step stage choropleth kept a ramp mixed for a page that no longer existed.

There is one copy now, and `mapPalette.test.ts` reads `globals.css` and fails if
any value stops matching the token it mirrors. It also asserts the ramp is
monotonic, that dark is the exact reverse of light, and that every mark clears
3:1 against the paper. A duplication that cannot silently drift is a different
thing from one that can.

| Mark | Ink |
|---|---|
| Data centre | **pen 1** — the count is pen 1 wherever it appears on this site |
| Substation 69 kV+ | pen 2 |
| Power plant | pen 3 |
| Mark halo | `--page`, so a dot reads as sitting on the paper |
| Stage 0–8 | nine steps along pen 2's hue, spanning `--seq-1`…`--seq-7` |
| Not placed on the scale | `--unmeasured-edge`, never a step of the ramp |

The same assignments hold on the front page's plot sheet, which is a
server-rendered SVG rather than MapLibre and so takes them from CSS: a facility
is pen 1 there too, and a facility located but carrying no power figure is an
open ring in `--unmeasured-edge`. Open rather than filled is the point — a small
filled dot would say a campus draws a little power, and it draws an unknown
amount.

Under those marks the sheet carries a coastline, and it is drawn in the paper's
own hairline rather than in any pen, because it is the one thing on that plate
that was not measured. It is dissolved from the same county boundaries that
decide which county every facility belongs to, so the shape a reader recognises
and the shape the data was assigned against cannot drift apart. Two earlier
versions had no coastline and asked the grid stipple to draw the country
instead; it never could, and the reason is worth keeping. A density field is a
measurement. There is nothing in Nevada to stipple, so Nevada had no edge, and
no amount of tuning the marks was going to give it one.

With the land carrying the shape, the 61,983 grid assets over it are free to say
only what they know. They are binned to a four-unit cell and weighted
logarithmically by how many fell in each. Four rather than nine, because binning
puts every mark on a lattice and a lattice is invisible while it is sparsely
filled and unmistakable once it is not: at nine units the populated half of the
country had something in nearly every cell and the layer read as a halftone
screen printed over the map. At four, occupancy drops to 30% and the
quantisation stops being a pattern the eye can find.

The basemap is CARTO's raster positron, near-white in light and near-black in
dark. Dropped straight onto chart paper it read as a hole punched in the page.
Tinting the tiles toward the paper was tried first and produced grey land inside
a sage page — a desaturated photograph rather than something printed. So the
tiles are made translucent and the paper is put behind them, which is the
truthful version of the same idea: the map is printed on the sheet and the sheet
shows through. Saturation is taken fully out, because the basemap is context and
the three pens are the subject.

MapLibre's own stylesheet is imported by the map component, which puts it after
`globals.css` in the bundle. Every rule re-skinning its controls is therefore
prefixed with `.map-container` so it wins on specificity rather than on order —
at equal specificity the zoom control stayed a white rounded card on the smoked
drum.

## Chart primitives

`apps/web/src/lib/recorder.ts`. Pure functions, no React, no DOM, no `fs`, so
the same code runs in a server component and a client one and the maths is
testable without rendering. Covered by `recorder.test.ts`.

`scaleLinear` · `niceTicks` · `stepPath` · `linePath` · `bandPath` ·
`dropFlatRuns` · `albersUsa` · `fitExtent` · `applyExtent` · `binToGrid` ·
`formatPeriod` · `formatCompact` · the shared month time base (`EPOCH_YEAR`,
`monthIndex`, `periodFromIndex`).

Two of these encode decisions rather than convenience:

- **`albersUsa`** is equal-area because the alternative on hand — plotting
  degrees straight onto the axes — stretches the north of the country sideways
  and would make the same number of facilities occupy more paper in Washington
  than in Texas. A test asserts the northern cell is narrower.
- **`dropFlatRuns`** is lossless for a stepped path, and the test asserts the
  invariant that matters: the sampled step function is unchanged, not that the
  path string is equal.

**No charting dependency**, reaffirmed 2026-08-01. A stepped line is a polyline
and an Albers conic is nine lines of trigonometry.

## Weight

The home page renders 1,853 facilities, 61,983 grid assets, a dissolved
coastline, three channels and twelve regional traces at **72 KB gzipped**, with
no map engine and no charting library. Three techniques carry it:

- Every layer of dots is **round-capped zero-length strokes**, bucketed by size
  or weight, so one `<path>` carries a whole bucket. A round cap on a path that
  goes nowhere paints a disc of the stroke's width.
- The grid underlay is binned to a cell before it is drawn at all.
- Both those paths, and the coastline, are written **sorted and relative**.
  Sorting the marks into row-major order costs nothing and takes the grid layer
  from 35 KB gzipped to 30, because neighbouring marks then share long prefixes;
  emitting the gap to the previous mark rather than its position takes it to 10,
  because in that order almost every gap is a one- or two-digit number. The
  coastline gets the same treatment: 954 vertices in 8.4 KB raw, 2.8 KB gzipped.
  On a closed ring the deltas have to be accumulated from what was actually
  written rather than from the ideal position, or 867 vertices of rounding error
  walk the end of the ring away from its start.

All of it matters double: this markup is emitted once as HTML and once into the
hydration payload. Measured on the same page: 520 KB raw and 124 KB gzipped with
absolute coordinates, 426 KB and 72 KB with sorted relative ones. Adding the
coastline and tripling the grid marks still left the page lighter than it was
before either change, because the encoding was the larger win.

## What the roll-out replaced

The fourteen inherited routes were built from the page structures this world's
own brief refuses, and rolling the world out is what removed them. Each is a
change of what a class *means*, not of where it is used, so the markup barely
moved:

| Was | Is | Why |
|---|---|---|
| `.card` — rounded panel, 1px border, drop shadow, stacked as page structure | A **sheet**: one neatline at the top, no radius, no shadow | Same-size boxes say every block weighs the same, and a shadow says a block floats above the page. Neither is true. |
| `.metric` × `.grid-4` — a row of hero-metric tiles | An instrument **parameter strip** under a rule | A big number in a box renders "measured, and zero" and "never measured" identically, which is the confusion the assertion classes exist to prevent. |
| `.eyebrow` above a heading | Deleted; one carried real provenance and moved below the title | The heading carries its own weight. |
| `.badge` — rounded pill, tinted fill | A **stamp**: word, edge colour, edge stroke pattern | Three redundant channels, so the claim survives greyscale, print, and colour vision deficiency. |
| `.notice` — 3px accent bar down the left | A ruled caution on the sheet | The bar spent the mark hue on a block that already says the same thing in its first four bold words. |
| `.guide-card` — grid of equal cards | Ruled **index rows** | A card grid says these all weigh the same; an index says they are a list you scan. |
| `.band` — bordered box in a table cell | The reading in the measurement face, under a rule that carries its step | A box in a row is a card inside a card, and it implied a category where the number is a continuum. |
| `--link` — indigo | Ink with a hairline underline | On a page whose argument is that colour grades a claim, a hue spent on "clickable" competes with the pens; a table of 276 county links rendered the densest page blue. |
| Body copy at **148–229 characters a line** | `--measure: 72ch`, capped on the text rather than on the container | Measured, not judged. A chart and a table are read by scanning across and take the page; a sentence is read by returning to the left edge and takes the measure. |

Two standing rules carried across unchanged:

1. Colour is never the sole carrier of a fact. Every stamp, pill and swatch sits
   beside a word that already states the case.
2. Ordinal quantities get a sequential ramp, not a set of unrelated hues.
   `--unmeasured` is deliberately not a faint step of that ramp, because a weak
   value and an absent value are different claims.

The perforated tractor-feed edge moved from the front page to `.shell`, so it
runs behind the header and past the footer on every route. It ran down one page
before, which made that page a different object rather than the first sheet of
one roll.
