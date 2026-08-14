# Radiology Operations Copilot

Radiology Operations Copilot is a synthetic, local-first portfolio prototype for radiology scheduling and imaging workflow operations. The primary product experience is now an Imaging Workspace for finding and reviewing synthetic studies; Scheduling Automation remains a separate first-class workflow. The implemented checkpoint combines deterministic workflow rules, strict AI-assisted referral extraction, real local Orthanc PACS interactions, human exception handling, and operational audit evidence. See `docs/imaging-workspace-pivot.md` for the product direction.

> **Safety statement:** This application is a synthetic portfolio prototype for healthcare operations workflow demonstration. It is not a production clinical system, medical device, diagnostic tool, or substitute for qualified healthcare and technical professionals. Do not enter real patient information.

## Primary workspaces

1. **Imaging Workspace** — the primary experience provides a clinical-first synthetic study worklist, study detail, series/content exploration, and secondary System Operations for PACS administration.
2. **Scheduling Automation** — synthetic referral intake/review, extraction, deterministic validation, slot recommendations, booking, cancellation, and rescheduling remain available at `/scheduling`.

The current Imaging Workspace is metadata-only. Viewer, longitudinal comparison, clinician-authored reporting, secure sharing, patient email, print/PDF, and EHR export are planned slices.

## Hard boundaries

- Synthetic data only; never real PHI.
- No image interpretation, diagnosis, clinical advice, or clinical appropriateness decisions.
- No DICOM deletion, pixel changes, identity-tag changes, or automatic patient merging.
- AI output is strictly validated, advisory only, and cannot execute privileged actions.
- Deterministic policy and backend RBAC run after AI output.
- Implemented authentication, scheduling recommendation/denial, referral, booking, transfer/denial, dispatch, and reconciliation decisions emit audit evidence. Correction and approval workflows are target-state work.

## Local architecture

The Compose stack defines Next.js, FastAPI, PostgreSQL, Redis, Celery worker/beat, source Orthanc, destination Orthanc, and MailHog. Hosted databases, managed authentication, cloud queues/storage, Vercel, and Supabase are explicitly deferred.

See:

- [Architecture decision](docs/adr/0001-local-first-modular-monolith.md)
- [Data model](docs/08-data-model.md)
- [API contract](docs/09-api-contract.md)
- [Risk and safety analysis](docs/10-risk-and-safety-analysis.md)
- [Implementation plan](docs/15-implementation-plan.md)

## Prerequisites

- Git
- Docker Desktop/Engine with Docker Compose
- Node.js 22+ (for host frontend tests)
- `uv` (for host backend tests)
- At least 8 GB RAM and 10 GB free disk; 16 GB RAM preferred

## Start the complete local stack

```bash
cp .env.example .env
# Replace every replace_with_* placeholder, including both occurrences of the database password, with unique local values.
docker compose up --build
```

Open:

- Application: <http://localhost:3000> (opens the Imaging Workspace)
- Scheduling Automation: <http://localhost:3000/scheduling>
- FastAPI docs: <http://localhost:8000/docs>
- API liveness: <http://localhost:8000/api/v1/health/live>
- Source Orthanc: <http://localhost:8042>
- Destination Orthanc: <http://localhost:8043>
- MailHog: <http://localhost:8025>

All published ports bind to `127.0.0.1` in the provided Compose file.

## Seeded local-only users

The seed creates fixed synthetic account identities for the scheduler, PACS administrator,
operations manager, auditor, and system administrator roles. Their passwords are not committed:
set the five `*_DEMO_PASSWORD` values in your ignored local `.env` before starting the stack.

## Host quality checks

```bash
# Backend
cd backend
env -u PYTHONPATH uv sync --group dev
env -u PYTHONPATH uv run pytest -q
env -u PYTHONPATH uv run ruff check app tests alembic
env -u PYTHONPATH uv run mypy app

# Frontend
cd ../frontend
npx --yes pnpm@10.14.0 install
npx --yes pnpm@10.14.0 test
npx --yes pnpm@10.14.0 typecheck
npx --yes pnpm@10.14.0 lint
npx --yes pnpm@10.14.0 build
```

`env -u PYTHONPATH` prevents unrelated host Python environments from leaking into backend checks on Git Bash.

## Stop or reset

```bash
docker compose down
# Destructive local demo reset only (removes synthetic volumes):
docker compose down -v
```

The reset command is an operator-run local development action, not an application endpoint.

## Current phase

Phases 1–2 deliver the local foundation and scheduling workflow. Phase 3 adds typed non-destructive Orthanc adapters, metadata-only inventory, deterministic synthetic DICOM seeding, idempotent Celery transfers, destination reconciliation, protected PACS APIs, and the PACS operations workspace. The product has now been repositioned around an Imaging Workspace; technical PACS operations remain secondary and the Scheduling Automation workflow is preserved. Viewer, timeline, reporting, sharing, and EHR export are the next product slices.
