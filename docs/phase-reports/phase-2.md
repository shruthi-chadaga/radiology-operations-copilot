# Phase 2 Report — Scheduling Automation

**Date:** 2026-07-19
**Status:** Implemented with explicit gate deviations; included in the pending Phase 1–3 checkpoint

## Delivered

- Synthetic patient, referral, extraction, location, service, schedule, slot, appointment, order, history, and exception persistence models.
- Alembic scheduling migration.
- Provider-agnostic strict `ReferralExtraction` contract, deterministic mock provider, and versioned safety prompt.
- Deterministic completeness/ambiguity policy separated from AI extraction.
- Human exception creation for failed deterministic validation.
- Deterministic, non-clinical slot filtering/ranking and explanations.
- Transactional booking with row lock, slot version check, active-appointment prevention, accession creation, history, and audit.
- Cancellation and rescheduling that preserve prior records, release/version slots, update orders, and append audit/history.
- Scheduling APIs for referral intake/list/detail/extraction/validation/ranking and appointment book/cancel/reschedule.
- Interactive scheduling dashboard with synthetic referral intake, queue, confidence, state badges, and extract/validate controls.
- Idempotent seed with 50 synthetic patients, 40 referrals, 5 locations, 10 services, and 300 slots.

## RED–GREEN evidence

Session work followed RED–GREEN for the listed behaviors, but the repository cannot prove per-change chronology because implementation and tests are entering history together in the checkpoint commit.

Historical phase gate (superseded by the checkpoint gate):

- Backend: **27 passed**.
- Ruff: **all checks passed**.
- mypy: **no issues in 39 source files**.
- Alembic offline SQL: scheduling and exception tables confirmed.
- Frontend: **3 tests passed**, TypeScript passed, ESLint passed, production build passed.

## Safety decisions

- The AI provider can return data only and has no action interface.
- Unexpected AI fields are rejected.
- Deterministic policy runs after extraction and is authoritative.
- Missing authorization, low confidence, sedation markers, unknown services, and inactive locations block booking and retain human review. The lower-level validator supports an identity-conflict flag, but detection/input wiring is deferred and is not claimed as an active API control.
- Slot ranking uses operational preferences only and makes no clinical suitability claim.
- No scheduling record is destructively removed during cancellation or rescheduling.

## Files changed

Primary additions are under `backend/app/ai`, `backend/app/scheduling`, `backend/app/exceptions`, `backend/tests`, `frontend/features/scheduling`, `frontend/app/scheduling`, and `backend/alembic/versions/0002_scheduling.py`.

## Remaining risks

- A connected concurrent-booking test against PostgreSQL remains hardening work.
- Browser interaction was unit/build verified, but a container-connected authenticated scheduling E2E run remains outstanding.
- MailHog communication and waitlist workflows are deferred to the shared-operations phase.
