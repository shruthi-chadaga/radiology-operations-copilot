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
- Human-authored report drafting, finalization, and correction for authorized roles

## Secondary technical experience

- PACS node health
- Inventory synchronization
- Source/destination transfers
- Reconciliation evidence
- Incident review with proposal, separation-of-duties approval, and bounded evidence recovery
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

## Report workflow status: complete

The reporting workflow is implemented for authorized imaging roles:

- Clinicians author draft reports; application code and agents never generate report findings, impressions, or any diagnostic content.
- Report versions are immutable and append-only; corrections create a new linked version instead of overwriting history.
- Draft updates, finalization, and corrections require the expected current version number; concurrent editors receive a deterministic conflict instead of silent overwrites.
- Finalized reports cannot be edited in place; only a correction against the finalized version is possible.
- Worklist report status follows draft, finalized, and corrected states deterministically.
- Every draft save, finalization, rejection, and correction is audited.

## Share allowlist status: delivered

Sharing of finalized reports is implemented as an explicit, auditable, revocable allowlist:

- Operators allowlist a recipient by label; the entry carries a mandatory expiry (1–336 hours).
- The recipient token is generated once at creation, shown exactly once in the UI, and only ever stored as a SHA-256 hash.
- `POST /api/v1/imaging/shares/resolve` lets a recipient exchange the token for a bounded view of the finalized report text — no patient identifiers, study metadata, or images are included.
- Resolution fails closed: expired, revoked, unknown tokens, and reports that have left the finalized state (e.g., correction pending) all return an identical 403 with no oracle distinguishing them.
- Revocation takes effect immediately and is audited (`imaging.share.created` / `imaging.share.revoked`), as is creation.
- Emailing a share link through the local MailHog SMTP relay **rotates** the token: a fresh token is generated (only its hash stored) and the previous token stops resolving immediately. The raw token exists solely inside that one message and never in logs or audit evidence; only the recipient's email domain is audited. Audited as `imaging.share.emailed`.
- A mock FHIR `DiagnosticReport` export is available at `GET /api/v1/imaging/reports/{report_id}/fhir` for finalized reports under read roles. It serializes the authored findings/impression into a LOINC-coded, synthetic-tagged resource for demonstration; it makes no external calls, sends nothing to any real system, and every export is audited (`imaging.report.fhir_exported`).

## Safety boundary

This product still does not interpret images, diagnose, measure anatomy, modify pixels, delete DICOM, merge patients, generate report text by automation, email patients, write to an EHR, execute remediation from an approval, or make clinical recommendations. Report finalization is a human action recorded with full audit evidence; no automated actor may finalize or alter authored report content. The synthetic viewer is a rendered-preview surface for workflow demonstration only, and every recovery path remains bounded and human-approved before any retry would ever be considered.

## Next phases

### Phase D — Share and export: complete

Allowlisted sharing, expiring token links with MailHog email delivery and rotation, and a mock FHIR `DiagnosticReport` export are implemented. Remaining optional additions: print/PDF rendering and an EHR-shaped mock receiver. Every delivery destination is explicit, audited, and revocable.

### Phase E — Acquisition and interoperability

Add real modality receiver standards only after the product workflow is validated: DICOM C-STORE, Modality Worklist, MPPS, DICOMweb, and a mocked or sandboxed EHR adapter. Keep all external integrations behind typed adapters and synthetic-only test fixtures.
