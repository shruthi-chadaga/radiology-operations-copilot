# Risk and Safety Analysis

This is a synthetic portfolio prototype, not a production clinical system, medical device, or compliance certification. Safe failure and human review take precedence over automation rate.

This register includes current controls and later-phase target controls. Incident classification, policy administration, approvals, and remediation actions described below remain Phase 4+ target state unless the Phase 1–3 implementation-status documents explicitly list them.

## Non-negotiable controls

- Never accept real PHI or present the product as safe for it.
- Never interpret images, diagnose, advise clinically, or infer urgency/appropriateness.
- Never delete DICOM studies/instances, change pixels, alter identity tags, merge patients, or purge audit evidence.
- Never allow model prose to call tools, adapters, tasks, SQL, or privileged actions.
- Strictly validate model JSON, then apply deterministic policy and backend RBAC.
- Audit implemented authentication, denial, validation, booking, transfer, dispatch, and reconciliation decisions; expand correction/approval/remediation audit coverage with those later workflows.

## Risk register

| ID | Risk / failure mode | Impact | Initial | Preventive controls | Detection / safe response | Residual |
|---|---|---|---|---|---|---|
| R-01 | Real PHI entered into referral/UI | Privacy breach | Critical | persistent warning; seeded synthetic patient reference; required literal attestation and `[SYNTHETIC]` source marker; local-only; no telemetry | reject unmarked/unattested intake; stop demo and reset if misuse is suspected | Medium |
| R-02 | AI infers diagnosis, urgency, contrast/sedation safety, or appropriateness | Clinical harm/misrepresentation | Critical | administrative-only schema/enums; prompt boundaries; mock default; no image input | schema/policy rejection; human exception; safety tests | Low–Medium |
| R-03 | Prompt injection in referral/log text | Unauthorized behavior or misleading output | High | delimit untrusted data; instruction hierarchy in prompt; no AI tools; `extra=forbid`; enum outputs | validation failure/low confidence → exception; audit attempt | Low |
| R-04 | AI proposes destructive/non-catalog action | Data loss/security change | Critical | enum-constrained actions; adapter exposes no destructive methods; deterministic allowlist | `POLICY_DENIED`; audit; human escalation | Low |
| R-05 | AI schema drift/malformed JSON | Wrong workflow state | High | strict Pydantic schemas, bounded retries/timeouts, contract tests | no state action; manual path remains available | Low |
| R-06 | Automatic patient identity correction | Misidentification | Critical | no identity-write method or endpoint; mismatch classified high severity | stop transfer processing; preserve evidence; human exception | Low |
| R-07 | Double booking race | Operational conflict | High | row lock, expected slot version, unique active-referral constraints, transaction | one request gets 409; concurrency test and audit | Low |
| R-08 | Retry loop/duplicate external action | Duplicate traffic/studies | High | **Current:** idempotency key, DB uniqueness, durable dispatch, and automatic Celery retries disabled. **Target Phase 4:** policy-governed bounded retry | duplicate requests resolve to the existing job; incident workflow is target-state | Low |
| R-09 | Reconciliation false positive | Missing/incorrect destination study considered complete | High | compare study UID, accession, synthetic patient ID, and Orthanc statistics-derived instance counts | mismatch outcome; no auto-close; high-severity exception for identity | Medium |
| R-10 | Orthanc unavailable/misconfigured | Workflow outage | Medium | timeouts; circuit-like bounded checks; startup does not wait forever | degraded status; incident/evidence; no API crash | Low |
| R-11 | Unauthorized PACS action or cross-domain privilege escalation | Unsafe action | Critical | backend permission matrix; no trust in UI; short sessions; exact configured Origin required for unsafe cookie-authenticated browser requests | 403 plus audit of denied attempt; role tests | Low |
| R-12 | System administrator weakens policy silently | Governance bypass | High | **Target Phase 4:** versioned policy, explicit kill switch, system_admin-only edit | **Target Phase 4:** before/after audit and manager/auditor visibility | Medium |
| R-13 | Audit mutation or missing evidence | Loss of accountability | High | no update/delete API; append-only service; transactionally write domain+audit where possible | audit completeness tests; DB privilege hardening documented | Medium |
| R-14 | Secrets/API keys exposed to browser, Git, logs, or AI records | Credential compromise | High | **Current:** env-only server secrets, `.env` ignored, redacted operational evidence. **Target:** automated frontend build secret scan | manual staged secret scan and local credential rotation; broader automated scanning is target-state | Low |
| R-15 | Malformed/adversarial DICOM metadata | Parser failure/log injection | High | **Current:** deterministic synthetic marker validation, strict bounded metadata schemas, no pixels in DB. **Target Phase 4:** broader field normalization/size policy | current sync rejects the complete unmarked batch; quarantine/exception workflow is target-state; never modify source | Medium |
| R-16 | Mail escapes laptop or contains invented appointment facts | Privacy/misinformation | High | **Current:** local Compose provides MailHog only and no application send workflow. **Target:** DB-owned deterministic communication fields | preview/send auditing is target-state | Low |
| R-17 | Synthetic data resembles a real person | Portfolio privacy/reputation | Medium | conspicuously fictional names/IDs/domains and generated dates; no copied records | data review/reset; synthetic label | Low |
| R-18 | Local services exposed beyond host | Unauthorized local access | High | **Current:** localhost-published edge/PACS/MailHog ports, operator-supplied credentials, unpublished PostgreSQL/Redis, segmented networks | manual Compose inspection and connected checks; automated environment verifier is target-state | Medium |
| R-19 | Dependency/container vulnerability | Local compromise | High | **Current:** lockfiles and non-root application containers where configured. **Target:** pinned digests, CI vulnerability scans, and broader least privilege | scan reports and update process are target-state | Medium |
| R-20 | Prototype represented as production-compliant or medical device | Legal/reputational harm | High | mandatory README/footer disclaimer and synthetic KPI labels | portfolio review checklist | Low |

## Deterministic policy order

1. Authenticate and authorize actor.
2. Validate request schema and entity state.
3. Confirm global automation switch is enabled for automated execution.
4. Validate AI payload strictly if AI was involved.
5. Ignore AI safety flags as authority; recompute category, action, risk, confidence, and evidence constraints.
6. Deny prohibited/non-allowlisted/security/configuration/identity/unknown action paths.
7. Enforce approval and separation from proposal where configured.
8. Enforce retry/idempotency/attempt limits.
9. Re-check external preconditions immediately before execution.
10. Execute only a typed adapter method and audit outcome.

## Human-control triggers

Human review is mandatory for identity conflicts, low confidence, unknown or conflicting evidence, sedation-marked cases, clinical ambiguity, unrecognized exams, security/permission/configuration changes, retries beyond one, batch reprocessing, metadata correction, manual incident resolution, and every destructive/non-allowlisted action (which remains unimplemented/prohibited).

## Safety evidence required before MVP completion

- Tests show no DICOM delete/tag/pixel/identity route or adapter method exists.
- Prompt-injected text cannot produce execution.
- Malformed/extra AI fields fail validation.
- Low-confidence outputs always create/retain review.
- Unknown and identity mismatch incidents cannot auto-remediate.
- Unauthorized users receive 403 and the attempt is audited.
- One retry maximum and idempotency are enforced under duplicate requests.
- Every covered automated action has an audit event.
- Safety analytics report destructive autonomous actions and identity auto-modifications as zero.
