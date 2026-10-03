# Radiology Operations Copilot

Radiology Operations Copilot is a synthetic, local-first portfolio prototype for radiology scheduling and imaging workflow operations. The primary product experience is an Imaging Workspace for finding and reviewing synthetic studies; Scheduling Automation remains a separate first-class workflow. The implemented checkpoint combines deterministic workflow rules, strict AI-assisted referral extraction, real local Orthanc PACS interactions, human exception handling, and operational audit evidence. See `docs/imaging-workspace-pivot.md` for the product direction.

The end-to-end path is implemented: referral intake and validation, conflict-checked booking, synthetic study receipt from a real Orthanc node, idempotent PACS transfer with deterministic reconciliation, a unified imaging worklist, watermarked study viewing with prior comparison, clinician-authored versioned reporting, controlled sharing and export, and audited incident remediation where approval provably executes nothing. See `docs/imaging-workspace-pivot.md` for the full scope and `docs/retry-executor-design.md` for the deliberately unbuilt retry executor.

> **Safety statement:** This application is a synthetic portfolio prototype for healthcare operations workflow demonstration. It is not a production clinical system, medical device, diagnostic tool, or substitute for qualified healthcare and technical professionals. Do not enter real patient information.

## Primary workspaces

1. **Imaging Workspace** (`/pacs-ops`) — synthetic study worklist with search and modality/status filters, study detail, series and content exploration, watermarked preview viewing with prior comparison, patient timeline, clinician-authored reporting, share allowlists, and a scoped incident approval console. System Operations for PACS administration sits alongside it.
2. **Scheduling Automation** (`/scheduling`) — synthetic referral intake and review, AI-assisted extraction with deterministic validation, slot recommendations, booking, cancellation, and rescheduling.

## Delivered capabilities

- **Referral intake** — raw text preserved verbatim; AI extraction validated by strict schemas; deterministic rules run after the AI, never instead of it.
- **Booking** — PostgreSQL transactions with row locks and version checks prevent double-booking; failures are closed, not retried blindly.
- **Study receipt** — metadata-only inventory from a real local Orthanc node; studies are matched to appointments on accession *and* patient ID together, so a collision cannot detach the wrong study.
- **PACS transfer** — `Idempotency-Key` required, bounded attempts, Celery dispatch outbox, and reconciliation that defines success from identifier and instance-count comparison rather than the adapter's own return value.
- **Imaging worklist** — one projection across appointments, orders, and studies; terminal review states never regress on re-sync.
- **Study review** — series browser, watermarked preview, and prior comparison for workflow demonstration only. No image interpretation, measurement, or prioritization.
- **Reporting** — clinician-authored drafts with version history; finalization requires an expected version number; corrections append a new version and never overwrite. No automated actor may write report content.
- **Sharing and export** — allowlisted recipients with mandatory expiry, revocable tokens stored only as hashes, bounded recipient payloads with no patient identifiers, identical fail-closed responses with no oracle, token rotation on email delivery, print/PDF, mock FHIR `DiagnosticReport`, and a local mock EHR receiver.
- **Incident remediation** — deterministic classification, durable evidence, supersession of stale proposals, and two-person approval that records intent only. There is no code path that acts on an approval automatically.
- **Interoperability surfaces** — Modality Worklist, QIDO-RS-style study query, and MPPS-lite procedure steps served from PostgreSQL so standards-shaped clients can be exercised before any wire protocol exists.

## Hard boundaries

- Synthetic data only; never real PHI.
- No image interpretation, diagnosis, clinical advice, or clinical appropriateness decisions.
- No DICOM deletion, pixel changes, identity-tag changes, or automatic patient merging.
- AI output is strictly validated, advisory only, and cannot execute privileged actions.
- Deterministic policy and backend RBAC run after AI output.
- Report text is human-authored; no automated actor may generate, interpret, or finalize findings.
- Every authentication, scheduling, referral, booking, transfer, reconciliation, reporting, sharing, export, incident, approval, and denial decision emits audit evidence.
- **Approval is not execution.** An approved remediation proposal performs no transfer and calls no adapter; a retry executor is specified but deliberately not implemented (`docs/retry-executor-design.md`).

## Local architecture

The Compose stack defines Next.js, FastAPI, PostgreSQL, Redis, Celery worker/beat, source Orthanc, destination Orthanc, and MailHog. PostgreSQL is authoritative for workflow, incident, and audit state; Redis and Celery sessions are not systems of record. Hosted databases, managed authentication, cloud queues/storage, Vercel, and Supabase are explicitly deferred.

Migrations run automatically on backend start (`alembic upgrade head`); the current single head is `0020_mock_ehr_deliveries`.

See:

- [Architecture decision](docs/adr/0001-local-first-modular-monolith.md)
- [Data model](docs/08-data-model.md)
- [API contract](docs/09-api-contract.md)
- [Risk and safety analysis](docs/10-risk-and-safety-analysis.md)
- [Implementation plan](docs/15-implementation-plan.md)
- [Imaging Workspace pivot](docs/imaging-workspace-pivot.md)
- [Retry executor design (not implemented)](docs/retry-executor-design.md)

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

## Delivered phases

| Phase | Scope | Status |
|---|---|---|
| 1–2 | Local-first foundation, synthetic scheduling workflow, referral intake, AI extraction with deterministic validation | Complete |
| 3 | Typed non-destructive Orthanc adapters, metadata-only inventory, deterministic synthetic DICOM seeding, idempotent Celery transfers, destination reconciliation, protected PACS APIs, PACS operations workspace | Complete |
| A/B | Imaging Workspace pivot, study detail and series browser, watermarked preview viewing, prior comparison, patient timeline, keyboard-accessible worklist | Complete |
| C | Clinician-authored reporting with immutable version history, optimistic-concurrency finalization, correction workflow | Complete |
| D | Share allowlist with expiring revocable tokens, token rotation on MailHog email delivery, mock FHIR `DiagnosticReport` export, print/PDF, mock EHR receiver | Complete |
| E (core) | Modality Worklist, QIDO-RS-style study query, MPPS-lite procedure steps | Complete |

## Remaining work

Deliberately not built, and why:

- **Retry executor** — specified in `docs/retry-executor-design.md` but intentionally unimplemented so that approval remains recorded intent rather than an automation trigger.
- **Wire-level DICOM protocols** — C-STORE/C-FIND over the network, MPPS as a service class, and DICOMweb transport. The current surfaces serve the same standards-shaped data from PostgreSQL so workflow can be validated first.
- **Production governance** — data retention, signing identity, clinical sign-off, and deployment controls.

## Verification status

Last full local verification: backend 178 tests, frontend 43 tests, Ruff/mypy/format clean, single Alembic head `0020_mock_ehr_deliveries`, fresh-database migration chain, connected Orthanc smoke, authenticated browser smoke, and an authorized local penetration exercise (`scripts/pentest_local.py`) that reported no critical, high, medium, or low findings.
