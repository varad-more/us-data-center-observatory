# Methodology

Helios does not claim who operates a facility unless a primary filing says so. It assembles public records into an evidence-backed timeline and an explainable confidence score.

## Assertion classes

| Class | Meaning |
|---|---|
| `reported` | Stated by an authoritative source |
| `extracted` | Parsed from a document with a citable locator |
| `calculated` | Deterministic derivation (e.g. acreage, distance) |
| `inferred` | Indirect conclusion; may be wrong |
| `predicted` | Model output about an unobserved state |
| `unknown` | Explicitly not established |

## Development stages (0–8)

Ordered from no known development through expansion. Stages can move forward or be **downgraded** when evidence is contradicted. Transitions are append-only in `site_stage_history`.

## Scoring model

- Name: `helios-rule-based` version `0.1.0` (`packages/helios_scoring/rules.py`).
- Each evidence kind maps to at most one rule with a base weight.
- Applied weight = base × confidence multiplier × recency multiplier (standing conditions skip staleness decay).
- Contributions saturate into 0–100 and are capped by **evidence diversity**.
- Weights are domain-reasoned starting points, **not fitted**. Calibration waits for a labelled backtest.
- Historical replay requires `is_backtest=True` so live site state is not silently rewritten.

Highest-weight early-warning rules (transmission/substation filings, backup-generator air permits) only fire when those connectors contribute evidence. Gaps are listed in `docs/limitations.md`.

## Area consumption

Per-site power and water figures are inferences from acreage, and on their own they have no scale: 40 MW is either negligible or alarming depending on what the surrounding area already draws. Helios therefore ingests the denominator from the agencies that measure it — USGS county water withdrawals, EIA state retail electricity sales, and EIA state generation capacity — and stores them in `area_totals`, a table separate from `site_estimates` so that nothing can sum an agency's measurement together with one of Helios's guesses.

Every area total is `reported`. The comparisons drawn against them are `inferred`, and the API returns the two as separate lists for that reason. Two conversions are involved and both are published with the figures they produce:

- Site water estimates are gallons per day; county withdrawals are millions of gallons per day.
- Site power estimates are a **capacity** in MW; retail sales are **energy** in MWh per year. Converting one to the other requires an assumed annual load factor (0.60–0.90, likely 0.75) applied over 8,760 hours. That assumption sits on top of the assumed power density already in the capacity figure, so the annualised number is weaker than the capacity it came from.

The third comparison — summed site capacity against reported net summer generating capacity — needs no conversion at all, since both sides are a peak figure in MW. It is the strongest of the three for that reason, and also the easiest to misread: **a share of total generating capacity is not a share of unused capacity.** Existing demand already consumes most of that figure, and Helios does not know how much. Net summer capacity is used rather than the more-quoted nameplate figure because it is what the grid can deliver on the afternoon that decides whether there is room. Whether any individual site can actually be served is an interconnection question, answered by filings Helios cannot read.

The two EIA files do not share a reference year: sales currently stops at 2020 while capacity runs to 2024. Each is published with the year it describes rather than aligned to the other.

Helios does not know substation capacity and does not estimate it. Neither HIFLD nor OSM publishes transformer capacity in MW, and FERC Form 715 is restricted as CEII. No substation carries a capacity or utilisation figure anywhere in the API or the UI.

## Site identity

Sites receive anonymous codes (`AZ-MESA-001`). Clustering requires spatial adjacency **and** related ownership. Under-clustering is preferred to fabricating a campus.

## Privacy

Natural-person owner names and owner mailing street addresses are redacted before persistence when policy flags are on (default). Assessor queries deliberately omit owner mailing street fields.
