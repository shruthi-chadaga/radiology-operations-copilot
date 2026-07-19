# API Endpoint Definitions

Base path: `/api/v1`. JSON uses RFC 3339 timestamps and UUID strings. Errors use `{ "code", "message", "details", "request_id" }`. Mutating requests accept/return correlation IDs; retry/external-action requests require `Idempotency-Key`. Authentication is an HttpOnly cookie plus CSRF protection for state-changing browser requests.

## Common rules

- All routes except `/health/live`, `/health/ready`, and login require authentication.
- Authorization is checked by the backend using scheduler, pacs_admin, operations_manager, auditor, and system_admin roles.
- List routes support `limit`, `cursor`, sort, and bounded filters.
- AI routes return validated structured DTOs plus model/prompt version and policy disposition.
- No endpoint deletes DICOM data, edits tags/pixels/identity, changes Orthanc global configuration, or accepts executable commands.

## Platform and authentication

| Method | Path | Roles | Purpose |
|---|---|---|---|
| GET | `/health/live` | public | Process liveness |
| GET | `/health/ready` | public | Database and Redis readiness; Orthanc reported but non-blocking |
| GET | `/health/worker` | authenticated | Bounded worker status |
| POST | `/auth/login` | public/rate-limited | Validate seeded account; set session cookies; audit outcome |
| POST | `/auth/refresh` | session | Rotate refresh session |
| POST | `/auth/logout` | authenticated | Revoke session; clear cookies; audit |
| GET | `/auth/me` | authenticated | Current user and permissions |

## Scheduling

| Method | Path | Main request/response | Roles |
|---|---|---|---|
| POST | `/referrals` | synthetic patient reference + source text/scenario → referral | scheduler, manager |
| GET | `/referrals` | filtered referral page | scheduler, manager, auditor(read) |
| GET | `/referrals/{id}` | referral, extractions, validation, exceptions, timeline | scheduler, manager, auditor(read) |
| POST | `/referrals/{id}/extract` | provider selection optional → strict extraction result | scheduler, manager |
| POST | `/referrals/{id}/validate` | current accepted fields → deterministic rule results | scheduler, manager |
| PATCH | `/referrals/{id}/fields/{field_name}` | corrected value + reason | scheduler, manager |
| POST | `/referrals/{id}/slot-recommendations` | preferences + date window → ranked eligible slots | scheduler, manager |
| POST | `/appointments` | referral, slot, expected slot version → appointment/order | scheduler, manager |
| GET | `/appointments` | filtered page | scheduler, manager, auditor(read) |
| GET | `/appointments/{id}` | appointment/order/history/communications | scheduler, manager, auditor(read) |
| POST | `/appointments/{id}/cancel` | reason → cancelled appointment/released slot | scheduler, manager |
| POST | `/appointments/{id}/reschedule` | new slot, expected versions, reason → revised booking | scheduler, manager |
| POST | `/waitlist` | referral/preferences/window → entry | scheduler, manager |
| GET | `/waitlist` | filtered entries | scheduler, manager, auditor(read) |
| POST | `/waitlist/{id}/offer` | eligible slot + expiry → queued local email | scheduler, manager |
| POST | `/communications/preview` | template/context → deterministic preview | scheduler, manager |
| POST | `/communications/send` | communication ID → MailHog status | scheduler, manager |

Conflict behavior: booking/rescheduling returns `409 SLOT_CONFLICT` or `409 ACTIVE_APPOINTMENT_EXISTS` without partial writes. Low-confidence, ambiguous, identity-conflict, sedation, unknown exam, and missing fields create/retain exceptions and never auto-book.

## PACS/RIS

| Method | Path | Main request/response | Roles |
|---|---|---|---|
| GET | `/pacs/nodes` | configured node summaries | pacs_admin, manager, auditor(read) |
| GET | `/pacs/nodes/{id}/health` | latest health evidence | pacs_admin, manager, auditor(read) |
| POST | `/pacs/nodes/{id}/health-check` | new bounded check | pacs_admin, manager |
| GET | `/pacs/studies` | normalized metadata page | pacs_admin, manager, auditor(read) |
| GET | `/pacs/studies/{id}` | metadata only; never pixels | pacs_admin, manager, auditor(read) |
| POST | `/pacs/studies/sync` | enqueue inventory sync | pacs_admin, manager |
| POST | `/pacs/transfers` | source/destination/study → idempotent transfer job | pacs_admin, manager |
| GET | `/pacs/transfers` | filtered jobs | pacs_admin, manager, auditor(read) |
| GET | `/pacs/transfers/{id}` | attempts/evidence/reconciliation | pacs_admin, manager, auditor(read) |
| POST | `/pacs/transfers/{id}/retry` | approval reference → policy decision/task | pacs_admin, manager |
| POST | `/pacs/transfers/{id}/reconcile` | compare source/destination metadata | pacs_admin, manager |
| GET | `/pacs/incidents` | filtered incidents | pacs_admin, manager, auditor(read) |
| GET | `/pacs/incidents/{id}` | evidence/classification/policy/actions/timeline | pacs_admin, manager, auditor(read) |
| POST | `/pacs/incidents/{id}/classify` | evidence → validated taxonomy result | pacs_admin, manager |
| POST | `/pacs/incidents/{id}/approve` | action ID + reason | pacs_admin, manager |
| POST | `/pacs/incidents/{id}/reject` | action ID + reason | pacs_admin, manager |
| POST | `/pacs/incidents/{id}/execute` | approved action + idempotency key → task | pacs_admin, manager |
| POST | `/pacs/incidents/{id}/resolve` | summary; human resolution only | pacs_admin, manager |

Execution rejects with `422 POLICY_DENIED` when action/category/risk/confidence/attempt/global-switch conditions fail and `403 FORBIDDEN` for role violations. Denials and unauthorized attempts are audited.

## Shared operations

| Method | Path | Roles |
|---|---|---|
| GET | `/exceptions` | permitted domain staff, manager, auditor |
| GET | `/exceptions/{id}` | permitted domain staff, manager, auditor |
| PATCH | `/exceptions/{id}` | assigned domain staff, manager |
| GET | `/audit` | auditor, manager, system_admin; domain-limited staff view related timelines |
| GET | `/audit/{id}` | same as audit list |
| GET | `/analytics/summary` | manager, auditor |
| GET | `/analytics/scheduling` | scheduler, manager, auditor |
| GET | `/analytics/pacs` | pacs_admin, manager, auditor |
| GET | `/policies` | manager/read, system_admin/write |
| PATCH | `/policies/{id}` | system_admin only; versioned change + audit |
| GET | `/settings/automation` | manager, system_admin |
| PATCH | `/settings/automation` | system_admin only; global kill switch |

There are deliberately no audit update/delete endpoints and no public sign-up/user-creation endpoint in the initial MVP.

## Structured AI contracts

`ReferralExtraction` contains only allowed administrative fields. Each field is `{value, confidence: 0..1, source_excerpt}`; the response adds `missing_or_ambiguous_fields`, `requires_human_review`, and `review_reasons`. Unknown properties are rejected.

`IncidentClassification` constrains category, severity, runbook ID, and proposed action to approved enums; includes confidence, evidence references, explanation, and advisory safety flags. Deterministic policy recomputes eligibility and approval requirements instead of trusting those flags.
