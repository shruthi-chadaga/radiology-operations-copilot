# Radiology Operations Copilot Implementation Plan

> **For Hermes:** Execute one vertical, testable phase at a time using RED–GREEN–REFACTOR. Update the phase report before moving on.

**Goal:** Deliver a locally runnable synthetic healthcare-operations portfolio MVP connecting referral scheduling to a dual-Orthanc transfer failure, human-approved retry, successful reconciliation, and complete audit timeline.

**Architecture:** Next.js frontend plus FastAPI modular monolith, PostgreSQL system of record, Redis/Celery jobs, dual Orthanc adapters, MailHog, and a provider-agnostic strict-schema AI layer. AI remains advisory; deterministic rules and RBAC control every action.

**Tech stack:** Next.js, React, TypeScript, Tailwind, Zod, FastAPI, Python, Pydantic, SQLAlchemy, Alembic, PostgreSQL, Redis, Celery, Orthanc, MailHog, Pytest, Vitest, Playwright, Ruff, and mypy.

## Phase gates

Every phase must: (1) begin with a failing behavior test where production logic is added, (2) pass focused and regression tests, (3) update architecture/API/test docs, (4) write `docs/phase-reports/phase-N.md`, and (5) list changed files, decisions, and residual risks.

## Phase 0 — Decisions and contracts

- Create ADR, repository structure, relational model, API contract, implementation plan, and risk/safety analysis.
- Cross-check every artifact against the detailed specification.
- Gate: all six artifacts exist and explicitly preserve hard safety boundaries.

## Phase 1 — Local foundation

1. Create repository rules, environment template, Compose topology, Makefile, and README.
2. Add backend package and failing health/config tests; implement liveness/readiness.
3. Add SQLAlchemy/Alembic foundation and initial shared/auth/audit schema.
4. Add failing auth/RBAC tests; implement seeded Argon2 users and HttpOnly-token login.
5. Add failing audit append-only tests; implement audit service and read API.
6. Add Redis/Celery worker ping and health behavior.
7. Add Next.js shell tests; implement synthetic banner, role display, and unmistakable Scheduling/PACS tabs.
8. Run backend unit/integration tests, frontend lint/type/unit tests, Compose config validation, then local HTTP smoke tests.

Acceptance: stack starts; user can log in; both tabs render; database/Redis/worker readiness is visible; a sample login audit event can be read.

## Phase 2 — Scheduling vertical slice

1. Add patient/referral/service/location/schedule/slot/appointment/order models and migrations.
2. Add strict `ReferralExtraction` schema, mock provider, prompt v1, malformed-output and prompt-injection safety tests.
3. Implement referral creation, extraction review, deterministic validation, and exception creation.
4. Seed conspicuously fictional referral scenarios, locations, services, and slots.
5. Implement deterministic slot eligibility/ranking with explanations that avoid clinical claims.
6. Implement transactional booking with row lock/version and active-referral uniqueness; prove concurrent double-booking prevention.
7. Implement cancellation/rescheduling with immutable history.
8. Build scheduling dashboard/detail/booking UI with loading, empty, success, and error states.
9. Run unit, API integration, and Playwright scheduling tests.

Acceptance: a complete synthetic referral can be extracted, reviewed, validated, ranked, and booked; incomplete/ambiguous/low-confidence/identity/sedation cases stop in exceptions.

## Phase 3 — PACS foundation and transfer

1. Add separate Orthanc source/destination configurations, volumes, credentials, and routing.
2. Define typed non-destructive PACS protocol and contract tests.
3. Implement bounded health checks and node dashboard.
4. Generate minimal non-clinical DICOM via pydicom with fictional identifiers and accession linkage.
5. Upload to source, normalize metadata (never pixels), and sync inventory.
6. Add transfer/attempt/reconciliation models and idempotent transfer creation.
7. Send source to destination, verify presence, compare identifiers/counts, and display evidence.
8. Run adapter contract and real-container integration tests.

Acceptance: healthy source-to-destination transfer succeeds and reconciliation evidence is stored; Orthanc unavailability does not crash API startup.

## Phase 4 — Incidents and safe remediation

1. Add deterministic incident taxonomy/severity detector tests and implementation.
2. Add strict `IncidentClassification` schema, mock classifier, approved runbook catalog, and prompt v1.
3. Add post-AI policy engine; test global kill switch, confidence, category/action allowlist, attempt cap, and approval requirements.
4. Create failure incident from destination-unavailable transfer.
5. Implement proposal/approve/reject workflow with backend RBAC and audited unauthorized attempts.
6. Execute one idempotent allowlisted retry after approval/restored health; reconcile before closing.
7. Prove identity mismatch, unknown, duplicate, authorization, configuration/security, destructive, and non-allowlisted actions cannot auto-execute.
8. Build incident detail UI and run unit/integration/E2E tests.

Acceptance: failed transfer becomes an incident; authorized approval permits exactly one safe retry; destination verification closes it; prohibited scenarios remain human exceptions.

## Phase 5 — Shared operations

1. Build cross-domain exception queue/detail and role-scoped updates.
2. Build immutable audit viewer with filters and decision evidence.
3. Add synthetic-labeled KPI queries and dashboards, including five zero-tolerance safety KPIs.
4. Add MailHog templates/preview/send for appointment and incident messages; deterministic facts come from DB.
5. Add versioned policy settings and global automation kill switch restricted to system admin.
6. Run role matrix, audit completeness, MailHog integration, analytics contract, and accessibility tests.

Acceptance: both domains appear in shared operations; all actions are explainable; local emails are visible in MailHog; policies cannot be edited by unauthorized roles.

## Phase 6 — Hardening and portfolio demo

1. Add one-command seed/reset, environment verifier, and connected demo runner.
2. Run the full scenario from referral to accession-linked study to failed transfer and approved retry.
3. Add security tests for prompt injection, malformed DICOM metadata, secret/log redaction, cross-domain privilege escalation, retry loops, and audit mutation.
4. Run Ruff, mypy, backend tests, frontend lint/type/unit tests, Playwright, Compose config, container health, Orthanc transfer, and MailHog smoke checks.
5. Perform accessibility keyboard/focus/label/contrast review.
6. Finalize README, architecture, AI governance, test strategy, UAT results, demo script, limitations, and deferred hosting plan.

Acceptance: `docker compose up --build` and documented commands reproduce the entire demo; destructive autonomous action count is zero; low-confidence escalation, audit coverage, and allowlist enforcement tests are 100% for covered cases.

## Test command targets

```bash
make format
make lint
make typecheck
make test
make test-integration
make test-e2e
make compose-validate
make demo-reset
make demo
```

## Local environment status

Docker Desktop 4.82.0, Docker Engine/CLI 29.6.1, Compose 5.3.0, Node.js, pnpm, `uv`, and WSL 2.7.10 are installed. The post-install restart completed, Docker's Linux engine is available, all nine Compose services start, and the connected Phase 3 Orthanc transfer gate passes.
