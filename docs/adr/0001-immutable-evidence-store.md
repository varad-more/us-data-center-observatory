# ADR 0001 — Immutable, content-addressed evidence store

## Status

Accepted (first sprint).

## Context

Helios conclusions must be independently verifiable. If source bytes can be overwritten, a later viewer cannot tell whether a score reflects the document Helios originally saw.

## Decision

1. Every fetched payload is stored under its **SHA-256** content hash.
2. The store is **append-only** in application code. Overwriting an existing hash is forbidden; identical content is a no-op.
3. Local development uses a filesystem backend (`HELIOS_EVIDENCE_ROOT`). Compose provides MinIO for an S3-compatible path.
4. Database rows (`document_versions`) reference the hash and metadata; they never embed mutable source bytes.
5. Evidence records cite a specific `document_version_id` plus a locator (JSON path, URL, or span).

## Consequences

- Re-ingesting unchanged sources creates no new versions and no new evidence (idempotency).
- Evidence bundles (`/exports/site/{id}/bundle.zip`) can ship the exact bytes used for a conclusion.
- Storage grows with distinct content; purge requires an explicit, audited process outside this sprint.
- Production S3 buckets should deny `s3:DeleteObject` for the evidence prefix.
