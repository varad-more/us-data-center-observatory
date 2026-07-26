# ADR 0002 — No Kafka and no Kubernetes for the first sprint

## Status

Accepted (first sprint). Referenced by `docker-compose.yml`.

## Context

The product vision mentions streaming ingestion and cloud-native deployment. For Phase 0 / first sprint the measured workload is:

- one study region (East Valley, Arizona);
- a handful of connectors run on demand or nightly;
- ingestion volume in the low thousands of records.

Kafka and Kubernetes solve problems we have not measured yet (fan-out between many consumers, multi-tenant scheduling, horizontal connector fleets).

## Decision

1. **Compose only** for local orchestration: Postgres/PostGIS, MinIO, API, web, optional worker CLI.
2. **Synchronous ingestion** via the `helios` CLI and admin API. No message broker.
3. **No Helm charts, operators, or cluster manifests** in this repository until a second region or continuous multi-source cadence forces the issue.
4. Connector runs remain process-local and idempotent so a later scheduler (cron, Cloud Run Jobs, etc.) can wrap the same entry points without rewriting pipelines.

## Consequences

- Operational surface stays small enough for one developer to reason about.
- Nightly refresh is `helios bootstrap` (or per-connector `helios ingest`) behind whatever scheduler the operator prefers.
- Adding Kafka/K8s later is an additive change; it must not rewrite the connector contract or evidence store.
- Agents and contributors must not introduce broker/cluster scaffolding “for completeness.”
