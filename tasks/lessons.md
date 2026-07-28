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
