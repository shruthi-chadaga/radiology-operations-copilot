# Phase 3 Report — PACS/RIS Foundation and Transfers

**Date:** 2026-07-25
**Status:** Complete; checkpoint committed and reproducible connected PACS gate added

## Delivered

- Typed `PacsAdapter` boundary and bounded Orthanc REST client.
- No adapter operations for deletion, pixel modification, tag-based identity modification, merging, or image interpretation.
- PACS node health evidence and metadata-only study inventory with non-destructive upsert semantics.
- Deterministic synthetic DICOM generator and idempotent source-seed command; generated objects contain no `PixelData`.
- PACS node, health, study, transfer job, attempt, and reconciliation persistence.
- Alembic migrations through `0008_transfer_dispatch_outbox`, including immutable transfer intent and durable dispatch recovery.
- Idempotent transfer creation with request consistency checks, one-retry ceiling, append-only attempts, redacted failures, correlation metadata, and audits.
- Celery transfer execution with automatic retries disabled until Phase 4 deterministic policy.
- Deterministic destination reconciliation for Study Instance UID, accession, synthetic patient ID, and instance count.
- Protected node, health, study, transfer, detail, and reconciliation APIs with backend RBAC.
- Separate source and destination Orthanc credentials sourced from environment settings only.
- PACS operations workspace for health checks, metadata inventory, transfer queueing, and job status.

## RED–GREEN evidence

Session work followed RED–GREEN for these behaviors, but the repository cannot prove per-change chronology because implementation and tests are entering history together in the checkpoint commit.

Current checkpoint quality gate:

- Backend test suite: passed.
- Ruff format/check: passed.
- mypy: passed.
- Alembic: a genuinely empty PostgreSQL database migrated cleanly through `0008`.
- Frontend: **9 tests passed**, TypeScript passed, ESLint passed, and production build passed.
- `docker compose config --quiet`: passed; all nine services rendered.
- `make test-integration`: starts the required containers, idempotently seeds only
  conspicuously synthetic DICOM, and verifies both Orthanc nodes plus metadata-only
  inventories through the real typed adapters.

## Safety decisions

- PostgreSQL stores normalized metadata and evidence only, never DICOM pixel data.
- Synthetic DICOM seed objects are conspicuously fictional, deterministic, and contain no pixel element.
- The adapter surface omits destructive and identity-changing operations by construction.
- Transfer creation requires an idempotency key and rejects reuse for a different request.
- A transfer completes only after deterministic destination reconciliation.
- Identity and count mismatches fail safely and retain human-visible evidence.
- External errors are redacted before persistence and audit.
- All mutable PACS routes are limited to PACS administrators and operations managers; auditors are read-only.

## Connected integration evidence

- WSL 2.7.10 and Docker Engine 29.6.1 started successfully after the Windows restart.
- All nine Compose services started; backend, PostgreSQL, and Redis health checks passed.
- Redis returned `PONG`; the Celery worker returned `pong`; Celery Beat remained running.
- Backend, frontend, both authenticated Orthanc endpoints, and MailHog returned HTTP 200.
- Live PostgreSQL migrated to `0008_transfer_dispatch_outbox` and retained the deterministic application seed and workflow history.
- Five deterministic metadata-only synthetic DICOM objects were uploaded to source Orthanc.
- Source inventory synchronized five studies with one instance each.
- One acceptance transfer executed once through Celery and reached `COMPLETED` with valid positive reconciliation evidence.
- Reusing an idempotency key returned the same transfer job and did not add an attempt.
- Persisted and API-visible reconciliation evidence recorded source count 1, destination count 1, matching identifiers, and outcome `matched`.
- The durable PostgreSQL dispatch row was published, Celery executed exactly one attempt, and explicit reconciliation advanced the transfer from `transferred` to `completed`.
- MailHog captured a synthetic-only SMTP smoke message without external delivery.
- Authenticated browser smoke on the configured `localhost` origin displayed both healthy PACS nodes, instance-counted synthetic inventory, and transfer history.
- The reproducible `make test-integration` gate rebuilt the backend, idempotently seeded
  five source objects, verified both real Orthanc nodes, read 5 source and 2 destination
  studies, and validated all returned records as metadata-only synthetic data.

One earlier historical row recorded a false `0/0 matched` outcome before count parsing was fixed. It is preserved as immutable historical evidence and is explicitly excluded from acceptance evidence; only the positive `1/1 matched` row above is valid.

## Connected defects corrected

- Celery Beat could not write its default schedule under the non-root `/app` directory; Compose now uses `/tmp/celerybeat-schedule`.
- Audit request/correlation identifiers were shorter than the public idempotency-key limit; migration `0004` aligns both at 160 characters.
- Orthanc expanded study data omitted instance arrays; the adapter now reads bounded `CountInstances` evidence from the study statistics endpoint, preventing false `0 == 0` reconciliation.
- The static header no longer claims the false role `demo viewer`; it accurately states that backend RBAC is active while the backend remains authoritative.
- Required credentials now come from operator-supplied environment values; Orthanc authentication was verified after rotation, and existing seeded-user password hashes reconcile without data reset.
- Compose separates edge, data, queue, PACS, and mail traffic; PostgreSQL and Redis have no host-published ports.
- The connected gate exposed a deterministic-seed contract mismatch: generated accessions
  use the specific `ACC-SP-*` prefix while validation previously required literal `SYN`.
  Validation now accepts that exact seed prefix while retaining required `SYN-*` patient IDs
  and `synthetic` study descriptions; arbitrary accession values remain rejected.
