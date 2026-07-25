# Phase 1 Report — Local Foundation

**Date:** 2026-07-19
**Status:** Implemented with explicit gate deviations; included in the pending Phase 1–3 checkpoint

## Delivered

- FastAPI health, local auth/RBAC, append-only audit service/API, SQLAlchemy/Alembic foundation, Celery configuration, and deterministic demo-user seed.
- Next.js/Tailwind application shell with persistent synthetic-only warning, local login, and primary Scheduling and PACS/RIS tabs.
- Dockerfiles and a nine-service Compose topology for frontend, backend, worker, beat, PostgreSQL, Redis, two Orthanc nodes, and MailHog.
- Safe local configuration, `.env.example`, Makefile, and README.

## Verification

- Backend unit/API tests, Ruff, and mypy passed at the phase gate.
- Frontend Vitest, TypeScript, ESLint, and production build passed.
- Host-started FastAPI and Next.js returned HTTP 200 on their smoke routes.
- Compose topology was parsed and structurally checked.
- The later connected gate started all nine services and verified backend health, PostgreSQL migrations, Redis, Celery worker/beat, both Orthanc nodes, frontend, and MailHog.

## Decisions

- Backend RBAC is authoritative; UI visibility is not a security boundary.
- AI defaults to deterministic mock mode.
- Audit mutation routes do not exist.
- All published Compose ports bind to localhost.

## Residual risk

Database-level append-only enforcement, readiness/worker APIs, and connected browser E2E coverage remain later hardening work. Durable PACS dispatch recovery was added during the checkpoint review.
