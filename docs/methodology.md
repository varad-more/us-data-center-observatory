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

## Site identity

Sites receive anonymous codes (`AZ-MESA-001`). Clustering requires spatial adjacency **and** related ownership. Under-clustering is preferred to fabricating a campus.

## Privacy

Natural-person owner names and owner mailing street addresses are redacted before persistence when policy flags are on (default). Assessor queries deliberately omit owner mailing street fields.
