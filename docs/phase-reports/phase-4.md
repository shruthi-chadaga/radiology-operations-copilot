# Phase 4 Report — Deterministic Incident Workflow

**Date:** August 10, 2026
**Status:** Incident classification, evidence persistence, human review, approval records, and bounded recovery are implemented; actual retry/remediation remains intentionally disabled.

## Delivered

### 1. Deterministic incident classification and policy

The incident classifier is a strict pure function with bounded inputs and no database, AI, adapter, or task dependencies. It classifies PACS evidence into connectivity, identity mismatch, count mismatch, unauthorized, configuration, destructive action, non-allowlisted action, unknown, or no incident. Identity/count evidence takes precedence over misleading generic network codes. Classifier results always contain `execution_authorized=False`.

The policy evaluator is fail-closed. Gates cover the global automation switch, configured retry limit, confidence, category, retry eligibility, action allowlist, attempt cap, destination identity-bound health freshness, healthy status, explicit approval evidence, approver role, and proposer/approver separation.

### 2. Persisted PACS incidents and recovery evidence

Added:

- `PacsIncident` model and migration `0010_pacs_incidents`.
- `IncidentPersistenceOutbox` model and migration `0011_incident_recovery`.
- `backend/app/pacs/finalization.py` recovery service.
- Focused incident persistence integration tests.

`pacs_incidents` has transfer/study/node foreign keys, a unique transfer-job key, explicit taxonomy/severity/status/approval/confidence checks, bounded redacted evidence, repeated-failure consolidation, and append-only creation/update audit events.

When inline incident persistence is unavailable, the transfer path writes a durable outbox item. The outbox is evidence for later persistence only; it never dispatches remediation.

### 3. Persisted proposal and approval workflow

Added migration `0016_incident_approval_controls` and two append-only workflow records:

- `incident_remediation_proposals` stores the allowlisted action, proposer identity/role, rationale, policy snapshot, and proposal state.
- `incident_remediation_approvals` stores exactly one independent approval or rejection decision, approver identity/role, reason, and current policy snapshot.

Protected APIs:

- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/{incident_id}/proposals`
- `POST /api/v1/incidents/proposals/{proposal_id}/approve`
- `POST /api/v1/incidents/proposals/{proposal_id}/reject`
- `GET /api/v1/incidents/outbox`
- `POST /api/v1/incidents/outbox/drain`

Role boundaries:

- PACS administrators and operations managers may propose.
- Operations managers and system administrators may approve or reject.
- Auditors may read but cannot mutate.
- Schedulers cannot access incident mutations.
- The proposer cannot decide their own proposal.
- Only `RETRY_TRANSFER` can be proposed.

An approval is explicitly recorded as **approval evidence, not execution authorization**. No adapter call, retry dispatch, or DICOM mutation occurs in this slice.

### 4. Incident-review UI

`frontend/features/pacs/incident-review-panel.tsx` is embedded under the existing System Operations disclosure. It supports:

- Refreshing incident evidence.
- Entering a proposal rationale.
- Approving or rejecting with a separate reason.
- Bounded outbox evidence recovery for approver roles.
- Visible no-remediation/no-retry messaging.

The Imaging Workspace, viewer, report workflow, Scheduling Automation, and System Operations structure remain intact.

## Verification

- Focused incident workflow tests: **5 passed**.
- Focused incident/classifier/policy/PACS tests: **51 passed**.
- Backend Ruff for the new slice: **passed**.
- Backend mypy for incidents and app registration: **passed**.
- Frontend typecheck: **passed**.
- Frontend focused and existing suite: **17 passed**.
- Frontend lint: **passed with one existing synthetic viewer `<img>` optimization warning**.
- Alembic head: `0016_incident_approval_controls`.
- Live migration against PostgreSQL remains environment-dependent because `DATABASE_URL` was not available in the validation shell.

## Remaining work

1. Do not execute an approved retry until a separate, audited executor is designed and tested; approval alone is intentionally insufficient.
2. Add a dedicated executor that re-evaluates policy, rechecks destination health, enforces idempotency, transfers once, reconciles, and closes the incident only after evidence is complete.
3. Add PostgreSQL migration and locking tests, including concurrent proposal/decision and incident consolidation cases.
4. Add connected Orthanc and browser end-to-end tests.
5. Make scheduling test fixtures relative to the test clock; the full backend suite still has five known date-sensitive scheduling failures.
6. Add retention, signing identity, operational notification, and clinical governance controls before any production use.

## Safety boundaries

No code in this slice interprets images, stores pixels, modifies DICOM content, deletes studies, merges patients, calls an AI provider, executes remediation, or automatically retries a failed transfer. Classification, persistence, proposal, approval, rejection, outbox draining, and UI actions are evidence/state operations only.
