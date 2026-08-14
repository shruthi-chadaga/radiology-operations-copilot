# Imaging Workspace Product Pivot

## Decision

The application presents the imaging workflow—not PACS infrastructure—as the primary product story.

The primary workspace is **Imaging Workspace**. The existing **Scheduling Automation** workflow remains a separate first-class workspace and its backend behavior was not changed.

## Phase A status: complete

Phase A connects scheduling context or PACS receipt into a persisted unified worklist and deterministic patient timeline. It includes durable projection records, statuses, priority, assignment-ready fields, report placeholders, and referral/appointment/study timeline events.

## Phase B status: complete

Phase B now provides a safe synthetic viewing checkpoint:

- A server-side Orthanc preview proxy retrieves only rendered PNG/JPEG previews, never original DICOM objects.
- Preview access requires an authenticated imaging role and a study marked with the existing synthetic inventory attestation.
- Preview requests verify that the requested Orthanc instance belongs to the selected study.
- The backend exposes current-study viewer context and deterministic prior candidates.
- Prior matching uses same synthetic patient ID, same modality when present, and an earlier study date. It does not compare pixels or make a clinical similarity judgment.
- The frontend displays current and selected prior previews with synthetic watermarking.
- Brightness control is a viewing affordance only; no measurement, diagnosis, AI interpretation, or image-derived recommendation is implemented.
- If rendering fails, the study metadata remains available and the UI explains the limitation.

### Phase B API surface

- `GET /api/v1/imaging/studies/{study_id}/viewer`
- `GET /api/v1/imaging/studies/{study_id}/preview/{instance_id}`

The endpoints are restricted to PACS administrator, operations manager, and auditor roles. No pixels are stored in PostgreSQL. The preview is returned with `Cache-Control: no-store` and `X-Synthetic-Preview: true`.

## Primary experience

- Unified imaging worklist
- Priority, workflow status, modality, accession, and patient context
- Patient timeline for referral, appointment, and received-study events
- Current/prior synthetic preview comparison
- Existing study content and technical tags on demand
- Planned reporting actions clearly marked as unavailable

## Secondary technical experience

- PACS node health
- Inventory synchronization
- Source/destination transfers
- Reconciliation evidence
- Technical study counts and storage node details

These remain available in the expandable **System Operations** panel for PACS administrators and operations managers.

## Current user flow

```text
Sign in
  ↓
Imaging Workspace
  ↓
Search/filter prioritized worklist
  ↓
Select a work item
  ↓
See patient timeline and study context
  ↓
Open synthetic viewer
  ↓
Compare current study with a deterministic earlier prior
  ↓
Open System Operations only when technical action is needed
```

Scheduler accounts continue to use `/scheduling`; scheduler login routing and backend automation remain unchanged.

## Safety boundary

This product still does not interpret images, diagnose, measure anatomy, modify pixels, delete DICOM, merge patients, finalize reports, email patients, write to an EHR, or make clinical recommendations. The Phase B viewer is a synthetic rendered-preview surface for workflow demonstration only.

## Next phases

### Phase C — Report workflow

Add clinician-authored draft reports, immutable report versions, role-aware signing/finalization, correction/amendment workflow, and audit events. AI may assist with administrative structure only; it must never be treated as a diagnostic authority.

### Phase D — Share and export

Add allowlisted internal sharing, expiring synthetic patient links through MailHog, print/PDF, and a mock FHIR `DiagnosticReport` export. Make every delivery destination explicit, auditable, and revocable where applicable.

### Phase E — Acquisition and interoperability

Add real modality receiver standards only after the product workflow is validated: DICOM C-STORE, Modality Worklist, MPPS, DICOMweb, and a mocked or sandboxed EHR adapter. Keep all external integrations behind typed adapters and synthetic-only test fixtures.
