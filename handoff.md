# Handoff — Imaging Workspace Phases A–D

**Date:** August 10, 2026
**Project:** Radiology Operations Copilot

## Current status

The product is an **Imaging Workspace** rather than a PACS transfer demonstration. Phase A (persisted worklist/timeline), Phase B (safe synthetic preview/prior comparison), Phase C (authored report workflow), and the Phase D incident-review slice are implemented as a local-first synthetic prototype.

It is not a production PACS, clinical system, medical device, diagnostic tool, or EHR.

## Phase D delivered

- Deterministic incident classification and fail-closed policy evaluation.
- Persisted `PacsIncident` evidence and incident-persistence outbox.
- Bounded outbox drain that persists evidence and never calls a PACS adapter.
- Persisted remediation proposals with rationale, proposer identity, and policy snapshot.
- Immutable approval/rejection decisions with approver identity, reason, and policy snapshot.
- RBAC-protected incident list/detail, proposal, approve, reject, outbox list, and outbox drain APIs.
- Proposer/approver separation of duties.
- Settings wired into approval snapshots and current policy checks: `enable_auto_retry`, `max_auto_retries`, and `low_confidence_threshold`.
- Incident-review panel embedded under System Operations.
- Explicit UI and audit messaging that approval is not execution.

### Phase D API

- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/{incident_id}/proposals`
- `POST /api/v1/incidents/proposals/{proposal_id}/approve`
- `POST /api/v1/incidents/proposals/{proposal_id}/reject`
- `GET /api/v1/incidents/outbox`
- `POST /api/v1/incidents/outbox/drain`

### Phase D role rules

- `pacs_admin` and `operations_manager`: propose.
- `operations_manager` and `system_admin`: approve, reject, and drain evidence outbox.
- `auditor`: read-only.
- `scheduler`: no incident workflow mutation.
- The proposer cannot decide their own proposal.

## Existing phases preserved

### Phase A — Imaging Workspace

Persisted imaging worklist projection, patient timeline, study context, and report-status integration remain intact. Scheduler records are not mutated by worklist refresh.

### Phase B — Synthetic viewer

Server-side rendered-preview proxy, synthetic-only authorization, instance ownership checks, current/prior comparison, authenticated Blob loading, brightness control, and safety watermark remain intact.

### Phase C — Authored reporting

Draft, immutable versions, finalization, correction workflow, synthetic-only access, role protections, audit events, and report editor remain intact.

### Scheduler and System Operations

Scheduling Automation remains first-class at `/scheduling`. The incident-review panel is inside the existing System Operations disclosure and does not replace or alter scheduler behavior.

## Verification recorded

- Full backend suite: **161 passed** (Ruff, mypy, and formatting clean).
- Frontend: **33 tests passed**, typecheck, lint, Prettier, and production build clean.
- Alembic head: `0017_incident_proposal_superseded` (single head).
- Fresh PostgreSQL database upgraded through the full migration chain; connected synthetic Orthanc smoke and an authenticated browser smoke test against the live Compose stack passed.
- Scheduling fixtures were converted to clock-relative dates, so the full suite no longer depends on the calendar.

## Remaining work

1. Design and implement a separate audited executor for an approved retry; do not treat the current approval record as permission to execute.
2. Re-evaluate policy and destination health immediately before any future execution.
3. Enforce one idempotent adapter call, then reconcile before incident closure.
4. Add production governance: retention, signing identity, notification, clinical review, and deployment controls.

## Safety boundary

No current Phase D code interprets images, stores pixels in PostgreSQL, modifies DICOM content, deletes studies, merges patients, invokes AI, retries transfers, or performs remediation automatically. It records evidence and human decisions only.
