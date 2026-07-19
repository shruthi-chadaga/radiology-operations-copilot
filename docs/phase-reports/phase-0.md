# Phase 0 Report — Planning and Architecture

**Date:** 2026-07-19  
**Status:** Complete

## Deliverables

- ADR for a local-first modular monolith and explicit trust boundaries.
- Proposed feature-oriented repository structure.
- Relational data model with booking concurrency and transfer idempotency invariants.
- Versioned API endpoint contract and role expectations.
- Six-phase implementation sequence with test gates.
- Risk register, human-control triggers, deterministic policy order, and required safety evidence.

## Files changed

- `AGENTS.md`
- `docs/adr/0001-local-first-modular-monolith.md`
- `docs/00-repository-structure.md`
- `docs/08-data-model.md`
- `docs/09-api-contract.md`
- `docs/10-risk-and-safety-analysis.md`
- `docs/15-implementation-plan.md`
- `.hermes/plans/2026-07-19_202336-radiology-operations-copilot.md`

## Important decisions

- Use a modular monolith rather than microservices for the laptop MVP.
- Keep AI advisory and typed; deterministic policy and RBAC are authoritative.
- Keep Orthanc integration non-destructive by interface design.
- Use PostgreSQL row locking/versioning for booking and database-backed idempotency for external retries.
- Make the deterministic mock AI provider the offline/demo default.
- Treat Orthanc availability as degraded readiness information rather than a startup blocker.

## Validation performed

Documentation artifacts were checked for required deliverables and explicit safety statements. No application production code was written in Phase 0.

## Remaining risks / environment blockers

- Docker is not currently available on Git Bash `PATH`, so Docker Compose, Orthanc, PostgreSQL, Redis, Celery, and MailHog cannot yet be executed or verified.
- pnpm is not currently available; Node.js is available and Corepack may be used to activate pnpm.
- The final authentication cookie/CSRF mechanism and local port exposure require implementation tests.
- Audit append-only behavior is an application-level control until database permissions/triggers are evaluated in hardening.
