# Lessons

Patterns worth not repeating. Updated after corrections and after bugs that got
through.

## Process

### Don't spawn subagents unless asked
Corrected mid-task: subagent launches were rejected. Do the exploration inline
with read-only tools. Reach for agents only on explicit request.

### Ask for direction before a large refactor
"Simplify this" had at least three readings that led to wildly different amounts
of deletion (frontend-only vs. keep-the-backend vs. hygiene). Asking first turned
a guess into a decision the user owned — and their answers inverted two of my
straw-man assumptions (they kept Terraform, dropped Compose).

### Establish a baseline before claiming a regression
Nine tests failed after my changes. Rather than guess, I stashed everything and
ran the suite on `HEAD`: the same nine failed. That one step separated
"I broke it" from "it was already broken" and took two minutes.

### `| tail` swallows exit codes
`pip install ... | tail -20` reported success while pip had failed — the pipeline
exit status is `tail`'s. When a command's success matters, capture `$?` from the
command itself or drop the pipe.

### Shell cwd persists between calls
A `cd apps/web` from an earlier command silently made `pip install -e "."`
resolve to the frontend directory. Use absolute paths for anything consequential.

## Engineering

### Test fixtures must mirror production wiring
The test session factory used SQLAlchemy's default `autoflush=True` while
production used `autoflush=False`. Tests therefore saw pending writes the real
application never would, and a bug where every site published a zero evidence
count passed green. If production configures a session, a connection, or a
client a particular way, the test harness must configure it identically.

### Replacing fake data with real data is a testing technique
Three genuine bugs — an out-of-vocabulary assertion class, zeroed evidence
counts, dead download links — were invisible for as long as the frontend was fed
hand-written mocks. The mock encoded what the author *believed* the backend
produced. Exporting real API output found the drift immediately.

### Fix the vocabulary violation, don't widen the enum
When the backend emitted `assertion_class: "estimated"` and the frontend enum
rejected it, the fast fix was to add "estimated" to the enum. That would have
enshrined a value the product's own epistemics don't define. The right fix was to
map it onto the existing, meaningful class (`inferred`) and add a test asserting
the vocabulary stays closed.

### Prefer the weaker epistemic claim
A power estimate is deterministic arithmetic over *assumed* coefficients. That
makes it `inferred`, not `calculated` — the formula is exact but the inputs are
industry assumptions. When choosing how strongly to label a derived value, pick
the more conservative class.

### Compute contrast, never eyeball it
An audit of the new palette found seven failures, and five were the badge borders
that the whole encoding depends on — borders measuring 1.73:1 and 2.49:1 still
look like borders to whoever picked them. The failure mode is invisible by
construction, so it needs a number. `make audit-contrast`.

### A ramp built for one obligation may not clear another
The sequential ramp is fine as a *fill*, which sits under a legible label and owes
nothing. Reused as badge *borders* — a meaningful mark owing 3:1 — its pale end
failed. Solving each step to the floor individually then collapsed them onto the
same value. Purpose-built tokens solved across the legal band kept the scale both
legible and monotonic. Ask what a token owes at each site it is used, not once.

### Greyscale-check any encoding that claims to survive greyscale
`unknown` and `predicted` both passed the contrast audit and were still the same
mark once hue was removed: luminance 0.292 against 0.288. Contrast against the
*background* says nothing about separation from a *sibling*. The fix was
structural — dotted versus dashed — because that is what actually survives.

### Testing Library cleanup does not self-register without `globals: true`
Renders accumulated in the document, so the second test to query a testid found
two and failed. One pre-existing test had passed only by being alone in its file.
Register `afterEach(cleanup)` in the setup file, not per test.

### Rollups belong in a pass after all mutations
Recomputing a denormalised counter inside the loop that mutates its inputs makes
the result order-dependent: a later iteration reassigned evidence and left an
earlier site's count stale. Compute aggregates once, after the writes settle.

### A column default can be load-bearing without anyone knowing
`Parcel.county` defaulted to `"Maricopa"`. Removing it turned CI red — not
because the default was needed, but because it had been silently filling a hole
left by an ordering bug: the loader added the parcel to the session, then
resolved its owner, and resolving an owner creates an organization, which
flushes. Before removing a default, ask what would be written *without* it and
at what moment. If the answer is "a half-built row, mid-function", the default
is not a convenience — it is a bug being paid for.

### Set every non-nullable column at construction
Not "before commit". Any intervening call that queries or writes can flush, and
a partially-populated object in the session is a row waiting to be written
wrong. Pass required values to the constructor, not to the object afterwards.

### An error recorder that shares the failing transaction destroys the evidence
The real violation was a single not-null error. What reached the log was
twenty-six foreign-key errors from the failure recorder trying to write
`ingestion_failures` rows against a `connector_runs` row the rollback had
already taken. The first exception never appeared anywhere. When diagnosing a
cascade, find the first failure by its *stage*, not by reading the loudest
error — and treat "the original exception is unreachable" as its own defect.

### Verify a third-party query parameter empirically before building on it
ECHO accepts `p_naics`, ignores it, and returns the unfiltered set. The
documented parameter is `p_ncs`. Both return HTTP 200 and well-formed JSON; only
the row count distinguishes them — 480 versus 15. A filter that appears to work
and does not is worse than one that errors. Four curl calls settled it; guessing
would have shipped a "national" query that filtered nothing.

### A nullable column inside a UNIQUE constraint is not constrained
Postgres treats NULLs as distinct, so `UNIQUE(a, b, sector)` enforces nothing on
any row where `sector` is NULL. The rows most likely to be NULL are usually the
common case — here, every water figure. Use a non-null sentinel (`"all"`) when a
column participates in a uniqueness key, and set it in the model, the migration
and the producer together.

### Capacity is not consumption
MW and MWh/yr are different quantities. Comparing an estimated capacity against
a reported annual energy total requires an assumed load factor, and that
assumption compounds with whatever assumptions already produced the capacity.
Do the conversion explicitly, in one named function, and publish the coefficient
next to the number — never inline the arithmetic at a call site where the
assumption disappears.

### Read the join key out of the source, do not recall it
Every county FIPS in the region registry was taken from the USGS file that
Helios filters on, not from memory. A misremembered code does not error: it
attaches one county's measured water use to a different county and renders as a
plausible number. When a key is the join between two datasets, the dataset is
the authority on it.

### Identical byte counts across different URLs mean a soft 404
Two different EIA download URLs both returned exactly 67,080 bytes with HTTP
200. Both were an HTML "page not found". A parser that trusts the status code
would have produced an empty result and reported success. Check the payload's
shape, not its status — `zipfile.is_zipfile` for an xlsx, a known header row for
a CSV — and make the check a test.

### A float sum straight out of SQL is not reproducible
`func.sum()` over 13 rows returned `551.7` in one export and `551.7000000000002`
in the next, from the same fixtures and the same code. Float addition is not
associative and Postgres promises no row order, so the last bit depends on the
plan. It reached the published snapshot as phantom drift. Round an aggregate to
the precision its inputs actually carry, at the point it leaves the query — and
assert that two identical requests return identical bytes, because this class of
bug is invisible in any test that compares numbers with a tolerance.

### Name a table for what it holds, not for the first thing put in it
`area_consumption` held county population within a day of being created, and
generation capacity within two. The name was already wrong before the second
source arrived. Renaming while the table is one migration old costs an
ALTER TABLE; renaming it after it has consumers costs an argument. When the
second row type does not fit the name, that is the signal, and it is cheapest
the moment it appears.

### The number most likely to be quoted needs the loudest caveat
"These sites are 1.68% of Arizona's generating capacity" reads as "there is
plenty of room". It is not that: existing demand already consumes most of that
capacity and Helios does not measure how much. A share of a total is not a share
of what is unused. Where a correct figure has an obvious wrong reading, put the
correction in the payload beside the number rather than in the docs, and assert
it in a test — a caveat that lives only in prose gets separated from the figure
the first time anyone quotes it.

### "Planned" and "withdrawn" are different promises
A registry entry marked `planned` tells a reader the connector is coming. HIFLD
substations are not coming — DHS withdrew public access. Reusing `planned`
because the enum happened to have no better member would have made the registry
state something false in the one place the project exists to be careful about.
The vocabulary is small and owned here; adding a member cost an enum entry, a
tone map and two tests, and no migration, because the value was already a plain
string end to end. Check what a status actually costs before bending an existing
one to fit.

### A mirror is not a source
Copies of the withdrawn HIFLD layer are still downloadable from university and
state ArcGIS servers, and ingesting one would have produced a national
substation table that looked exactly like the real thing. Its provenance would
have been "someone's undated copy of a dataset the publisher took down", with an
empty copyright field. Ingesting it degrades the graph precisely because the
output is indistinguishable from a good source. When the publisher has withdrawn
a dataset, the honest position is the gap, not the mirror.

### Check that a declared reason actually reaches the reader
The registry recorded why each blocked source was blocked, the sources page had
a component to render it, and five of six never appeared, because the API read
the field off the connector row and blocked sources have no connector. The test
that should have caught it asserted the invariant only for `fixture_only` — the
two entries that happen to have connectors — so it passed for a year while
saying almost nothing. When a test filters to a subset before asserting, check
whether the subset excludes exactly the cases the assertion is for.

### One encouraging probe is not a measurement
The hypothesis that county parcel data could be read by one connector per
*platform* rather than one per county survived exactly one test — Loudoun
County answering a standard ArcGIS REST query — and was reported as a finding
before the second test ran. It failed the second test, and the third, for a
different reason each time: the layer carried no ownership; the follow-up probe
searched for "parcels" when ownership rides on layers named "Assessor"; and the
corrected probe returned Charlottesville for Loudoun, a streets layer for Santa
Clara, and nothing for the one county already known to work. A claim built from
a single successful probe is a hypothesis wearing a result's clothing. Run the
negative cases, and include a case whose answer is already known — Maricopa
returning nothing is what exposed the third probe as noise.

### Automated discovery re-opens the mirror problem
Searching open-data portals by keyword to find a county's parcel layer returns
wrong-jurisdiction layers and private republications alongside authoritative
ones, and at the API surface they are indistinguishable: same protocol, same
field shapes, plausible names. A discovery-driven connector would have ingested
a private firm's copy of Dallas County parcels as county-authoritative. This is
[the HIFLD mirror problem](#a-mirror-is-not-a-source) reached from the opposite
direction — there by looking for a withdrawn source, here by automating the
search for a live one. Naming the authoritative endpoint stays a human decision.

## A parameter that looks like a selector may be a page size

ECHO's `responseset` was set to `1` and read as "which result set". It is the
number of rows per page. The connector then fetched only page one, so a national
query matching 447 facilities ingested a single row and reported success.

Nothing caught it for the same reason nothing caught the hardcoded `"AZ"`: six
cities in one state is a scale at which a paging bug and a fabricated state
constant both look like working code.

**How to apply:** when a query is widened by an order of magnitude, re-derive
what every request parameter means rather than assuming the old value still fits.
Check the row count the source reports against the row count actually loaded, and
surface the difference — a connector that silently returns 1 of 447 is worse than
one that fails.

## Reported and delivered and distinct are three numbers

The first fix compared de-duplicated rows against the source's headline count and
raised "ECHO reported 447 and returned 440" — a coverage gap that did not exist.
ECHO delivered all 447; seven repeated a RegistryID.

**How to apply:** before reporting a shortfall, separate *what arrived* from *what
survived processing*. A warning that misdescribes its own cause is worse than
silence, because it spends the reader's trust on a non-event. This is the same
principle as [[a-declared-reason-that-never-reaches-a-reader]]: the wording of a
gap is part of the gap.

## Zero rows under 429 is not zero rows

Checking whether four suspicious fixture records exist in live ECHO returned
nothing — because the API was throttling after a recording session. That is
absence of data, not data showing absence, and treating it as the latter would
have justified deleting published evidence.

**How to apply:** an empty result is only evidence when the request succeeded.
Check the status code before drawing a conclusion from a count, and when the
check is inconclusive, record the open question instead of resolving it in
whichever direction is convenient. Same failure mode as the county-parcel probe.

## A response can carry every record and still be useless

Asking ohsome for `properties=tags` returned every contribution with an id, a
timestamp and no flag saying whether it was a creation, a deletion or an edit.
Nothing errored. The rows were real and complete; they simply could not be
classified, so the parser skipped all of them and the history came out empty.
Only a proportional guard caught it — 3,377 of 4,629 unusable is a malformed
request, not sparse data.

**How to apply:** when a parser skips a record, count the skips and compare them
against the total. A handful is sparse data; a majority is a bug in the request.
Assert on the ratio, not on the presence of output, because output that parses
cleanly and means nothing looks exactly like success.

## The record of a deleted thing has no geometry

Every one of 232 removals arrived from ohsome with `geometry: null` — by the time
an element is deleted there is nothing left to take a centroid of. The parser
required a coordinate pair, so it dropped all of them, and the resulting counts
could only ever rise. A monotonically increasing "net" count is the tell.

**How to apply:** an event about a thing's disappearance cannot be assumed to
carry the thing's attributes. Resolve them from earlier events, and if a series
that is defined as net movement never moves downward, treat that as a bug to
disprove rather than a finding.

## A partial output file can poison every later run

A 46-row `events.csv`, written when a backfill was nowhere near complete, was
enough to flip every subsequent run into incremental mode: each asked for the
last five weeks and treated the preceding fourteen years as already covered. The
backfill could never finish, and nothing reported an error.

**How to apply:** never infer "the expensive work is done" from an artefact
merely existing. Gate the cheap path on a marker written only when the expensive
path actually completed, and make absence of the marker mean "do the full work" —
the safe direction is redoing effort, never silently skipping it.

## A window boundary can make a count go negative

Elements created before the history window and deleted inside it subtracted
facilities the series had never added, and the national count read minus one data
centre through 2012–2014. The arithmetic was right; the population was not.

**How to apply:** when a series is built from paired events, check that both
halves of the pair fall inside the window. Sanity-check derived series against
their own domain — a count of physical objects below zero is a bug that no
amount of correct summation will surface on its own.

## A pivot has to reach the front door

Nine new pages shipped for the pivot — growth, regions, 324 region details, the
national map, changes — and the page that introduces the project was never
touched. It still opened on "East Valley, Arizona · Maricopa County" and linked
to none of them. Every new page was correct and the site as a whole still
described the wrong project, because the entry point was the one page the new
work gave no reason to open.

**How to apply:** when the scope of a project changes, the pages that frame it
are part of the change, not documentation of it. After building a feature, open
the site at its root the way a stranger would and check that the path to the new
work exists. Navigation labels count: "National map" and "Site map" sat side by
side meaning entirely different datasets.

## Publishing a figure is not the same as making it legible

The site published megawatts, gallons and footprints for months without ever
saying what a data centre contains, why capacity is quoted in power rather than
floor area, or why cooling spends water. Every number was sourced, labelled by
assertion class and traceable — and unreadable to anyone not already in the
field, who could not tell whether 1,020 MW in one county was a lot.

**How to apply:** rigour about *where* a number came from does not substitute for
explaining *what it means*. When a project publishes a domain's quantities, it
owes that domain's concepts too. Derive the explanatory figures from the
committed data at build time so the teaching text cannot drift from the tables
beside it — the footprint spread quoted as the reason for weighting by area was
263:1, not the 30:1 carried over from a single county's numbers.

## An effect that sets state it depends on cancels its own work

The grid layer fetched on demand. The effect guarding that fetch listed
`gridState` in its dependencies and set it to "loading" on its first line, so
React re-ran the effect immediately, the re-run's cleanup flipped the
`cancelled` flag, and every handler on the in-flight request became a no-op.
The layer would have loaded never. Worse, the failure path was cancelled too,
so the map sat on "loading grid…" indefinitely and reported nothing.

Nothing structural caught it. Types passed, lint passed, the build produced all
351 pages, the rendered HTML was correct, and the file was served. It was found
only by a component test that clicked the control and looked for the layer.

**How to apply:** an effect must not write state that appears in its own
dependency array. Carry "already started" in a ref, which does not take part in
the comparison. More generally, when a feature cannot be verified by looking at
it, write the test that exercises the interaction rather than trusting that
every static check passing means it works — those checks all pass on a feature
that does nothing at all.

## A shared unit is not a shared quantity

Three kinds of polygon carried a data-centre tag: a building's floor plate, the
land boundary of a campus, and a site under construction. All three came back
from Overpass as an area in square metres, so the pipeline added them up and
called the result "footprint". Weighting a national electricity total by that
sum sent 82% of it to geometry that is not a building, and 19.7% to sites that
do not exist yet.

Nothing looked wrong. The allocation summed to the published total exactly, the
conservation check passed, every figure was derived from committed data, and the
ranking it produced was plausible enough to publish and leave up. It was visible
only in a consequence: Racine County drew 1,028 MW from five elements while
Loudoun County, the densest in the world, drew 1,020 from two hundred and
thirty-nine.

The same conflation had also written the *justification*. The footprint spread
quoted as the reason for weighting by area — 263-fold nationally, 34-fold in
Loudoun — was a land parcel divided by a building. Between buildings it is
12-fold and 4-fold.

**How to apply:** before aggregating a quantity, ask what physical thing each
value measures, not what unit it is in. Matching units are not evidence of a
matching quantity, and a sum of unlike things fails silently — it produces a
number, it balances, and it is wrong. When a source is a folksonomy like
OpenStreetMap, one tag routinely spans several physical kinds; check the
distribution of the *other* tags on the rows before trusting the column. And
treat an implausible ranking as a defect report about the model rather than a
finding about the world.

## Check the sentinel values a vocabulary reserves

Classifying those polygons, `'building' in tags` counted `building=no` as a
building. It is an explicit statement that the area is *not* one, and it carried
a 2 km² land parcel that put Valencia County, New Mexico second in the nation on
six elements. Caught only by re-reading the outlier instead of accepting a
result that had just moved in the direction I expected.

**How to apply:** a key's presence is not its truth value. Enumerate what a
field actually contains before branching on it — `Counter(tags.get(k))` over the
real data takes seconds and would have shown `no` sitting there among the 21
values. And be most suspicious of a new result exactly when it confirms the fix.

## Determinism has to be checked from a clean checkout, not from mtimes

The obvious gate for "is this derived file stale?" is comparing modification
times against its input. It cannot work: git stores no mtimes, so every file in
a fresh clone is equally new and the check passes on exactly the machine where
it matters. The working version rebuilds and diffs the bytes.

Getting there exposed the real defect. `meta.json` wrote a wall-clock
`generated_at`, which meant every offline rebuild produced a diff — so the
README's claim that "a poll with no upstream change produces no diff" had been
false for as long as the field existed, and no gate could have been added
without noticing.

**How to apply:** before writing a check for a property, run the thing twice and
confirm the property actually holds. One field of nondeterminism invalidates it
entirely, and a timestamp is almost always that field. Ask what the value is
*for* — nothing rendered `generated_at`, and the useful date was when the source
was last contacted, which is stable.

## Verify a negative result before trusting it

The drift gate reported PASS on a deliberately mutated file. The mutation had
not survived — `python` was not on PATH, the rebuild never ran, and the command
exited 0 anyway. A green mutation test is a claim that the gate is broken, and
it deserves the same scrutiny as a red one.

**How to apply:** when a test fails to fail, check that the code under test ran
at all before concluding anything about it. Echo the intermediate state — here,
the value in the file before and after the rebuild — rather than only the final
verdict.

## "CI is green" is not "I proofread it"

I had reported the repo verified and production-ready. A proofread then found
three defects that every check passes over, because none of them is a thing a
check was ever written to look at:

- The front page titled its chart "2012 to today" while the series starts
  2015-07. 2012 is `HISTORY_START`, the ohsome query window. The chart's own
  `aria-label` derived the real range, so a sighted reader and a screen-reader
  user got two different answers from one figure.
- 114 links across 13 pages read "View original evidence" and pointed at
  `https://example.invalid/recorded`, a TLD reserved so it can never resolve.
- A limitations heading announced two gaps and its paragraph described one.

All three are agreement failures between prose and the thing the prose
describes. Tests assert what the code does; they do not read the sentence beside
the number and ask whether it is still true. Hardcoded values in copy are where
this collects, because they are written once against a dataset that then moves.

**How to apply:** proofreading is its own pass, and it reads the *rendered*
output, not the source — 351 built pages scanned for `undefined`, `NaN`,
placeholder text and dead hosts is a minute's work and is the only view that
matches what a reader sees. Grep copy for hardcoded years and counts and check
each against the data; prefer deriving them, as the LBNL growth multiple on the
same page already does. And when a component computes a description twice —
once visibly, once for assistive tech — diff the two, because a disagreement
there is a defect that reviews and screenshots both miss.

## Changing the shape of an artefact means re-reading whatever asserts its shape

`trailingSlash: true` moves every route from `<route>.html` to
`<route>/index.html`. Verifying the new build is not enough — 352 pages, every
internal link resolving, CNAME emitted, assets at `/_next`, all correct — because
`test -f out/sites.html` is asserted *twice* outside the build, once in
`pages.yml` and once in `ci.yml`. Fixing the copy that failed first leaves the
other one to fail next.

A build-shape change has a blast radius wider than the build: deploy guards,
path assertions in CI, anything that hardcodes a filename. Verifying the new
output is right is a different question from asking what else in the repo holds
an opinion about the old output — and the answer is rarely one place.

**How to apply:** after changing an output layout, grep the *whole repo* for a
distinctive fragment of the old shape (`out/sites.html`) rather than opening the
file that complained, and run every workflow's assertions locally before
pushing. They are a handful of `test -f` lines that execute in a second, and
they are exactly what would otherwise stop CI three minutes later.
