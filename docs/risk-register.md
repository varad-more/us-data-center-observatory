# Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Scraping ACC/eCorp violates ToS or triggers blocks | Med | High | Fixture-only / planned status; no viewstate automation; document gaps |
| R2 | Storing natural-person PII from assessor | Med | High | Omit mailing street in query; redaction classifier; policy flags default on |
| R3 | Registry claims false connector coverage | Med | High | Importability test for runnable entry points; status enums enforced |
| R4 | Overconfident scores without backtest | High | Med | Diversity caps, saturation, explicit “not fitted” docs; no ML this sprint |
| R5 | OSM incompleteness read as absence | Med | Med | Reliability score 0.7; methodology + UI copy forbid negative inference |
| R6 | Historical `as_of` corrupts live stages | Low | High | Require `is_backtest=True` |
| R7 | Idempotency failure → duplicate evidence | Med | Med | Content-hash versions; integration tests for unchanged re-ingest |
| R8 | EPA throttle during demos | Med | Low | Self rate-limit; fixtures; graceful health/error messages |
| R9 | Address-only permit matching mis-links sites | High (when built) | Med | Defer Mesa permits until geospatial correlation tested |
| R10 | Scope creep into satellite/K8s | Med | Med | ADR 0002 + HANDOFF scope lock |

Review this register when adding a connector or changing PII policy.
