# Design: Audited Retry Executor (Approved-Remediation Execution)

Status: **DESIGN ONLY — NOT IMPLEMENTED.** This document is the contract any
future implementation must satisfy. The current system deliberately stops at
"approved": an `IncidentRemediationApproval` record proves a human decided a
retry *may* happen; it never causes one.

## 1. Why this component stays unbuilt for now

The most dangerous line in the product is between "a human approved a retry"
and "software performed a retry." Crossing it without exhaustive safeguards
converts an audit trail into an automation trigger. Every invariant below
exists to keep that crossing deliberate, bounded, and fully evidenced.

## 2. Trigger model

- An executor run is **only** started by an explicit, separately
  authenticated human command referencing a specific proposal ID.
- Approval records are **inputs to review, not triggers**. A scheduled worker
  MUST NOT scan approvals and act on them.
- Requiring the operator to re-state intent ("execute approved retry
  `<proposal-id>`") re-establishes separation between deciding and doing.

## 3. Pre-flight gate (all must pass atomically under one row lock)

1. Proposal status is exactly `APPROVED` and not superseded.
2. The incident is still open and still classified as retry-candidate.
3. Policy re-evaluation passes **at execution time**: automation enabled,
   confidence above threshold, category allowlisted.
4. Destination health re-checked live within `MAX_HEALTH_AGE_SECONDS` (300 s).
5. No prior successful execution exists for this proposal (idempotency key =
   `proposal:<id>`); one attempt per approval, ever.
6. Attempt budget: `retry_count < maximum_retries AND maximum_retries <=
   settings.max_auto_retries (<= 1)`.

Any failure → durable `executor.blocked` audit event with the failing check;
no partial work.

## 4. Execution envelope

- Exactly **one** adapter call (`send_study`) per approved attempt, executed
  inside the existing idempotent transfer-job machinery (dispatch outbox +
  reconciliation). The executor does not invent new PACS interaction paths.
- Hard wall-clock timeout; timeout = failed attempt with preserved evidence.
- On failure: transfer job enters the existing failure path (durable evidence,
  outbox incident persistence, reconciliation-mismatch rules). The executor
  adds no second failure-classification mechanism.

## 5. Post-execution duties

- Reconcile before any success claim: outcome derives from
  `ReconciliationResult`, never from adapter return value alone.
- Incident resolution only after a matched reconciliation; mismatch follows
  the existing incident-creation rules.
- Audit events: `executor.started`, `executor.attempt.recorded`,
  `executor.reconciled`, or `executor.failed`/`executor.blocked` — all with
  before/after state, `execution_authorized` reflecting reality for that step,
  and correlation ID binding proposal ↔ attempt ↔ reconciliation.

## 6. Explicit non-goals (forever)

- No automatic re-triggering, queueing, or scheduling of executions.
- No batch execution across proposals.
- No credential access beyond the existing adapter configuration path.
- No weakening of kill switch: `enable_auto_retry=false` blocks execution
  regardless of any approval.
- No DICOM deletion/modification, patient merging, or clinical judgment.

## 7. Required verification before implementation may merge

- RED tests for every blocked branch of the pre-flight gate.
- Concurrency proof: two simultaneous execute commands on one proposal yield
  exactly one attempt (unique constraint on idempotency key + row lock).
- Kill-switch proof: approval + fresh health + automation disabled → blocked.
- Full safety review by an independent reviewer against this document.
