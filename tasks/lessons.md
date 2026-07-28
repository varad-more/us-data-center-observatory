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
