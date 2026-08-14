# Code Bridge + FreeBuff Radiology Operations Copilot Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Install and verify Hermes Code Bridge, connect Hermes to the official FreeBuff CLI, then orchestrate isolated FreeBuff agents to converge the current Radiology Operations Copilot pivot into a safe, tested, documented, commit-ready checkpoint and continue toward the complete synthetic portfolio product.

**Architecture:** Hermes remains the control plane and final verifier. Hermes Code Bridge provides session-first routing, prompt structure, process tracking, and evidence rules; the official `freebuff` CLI is the execution backend. Every write-capable worker runs in an isolated Git worktree, follows RED–GREEN–REFACTOR, produces a local commit, and is followed by a fresh read-only FreeBuff review before Hermes integrates it. FreeBuff Desktop's private bundled orchestrator is not reverse-engineered or automated.

**Tech Stack:** Hermes Agent 0.20.1, Hermes Code Bridge 1.1.0 pinned to reviewed revision `69f97ab148282966979123bb466105bcb2a3bbc4`, FreeBuff CLI pinned initially to npm package `freebuff@0.0.149`, Git worktrees, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis/Celery, Orthanc, Next.js, React, TypeScript, Vitest, Ruff, mypy, ESLint, Prettier, Docker Compose.

---

## 1. Current Context and Non-Negotiable Assumptions

- Repository: `C:/Users/abhin/radiology-operations-copilot`
- Branch/upstream: `main` / `origin/main`
- Current state: 21 modified files, 49 untracked files, 0 staged files.
- Current changes are **not commit-ready** and include safety-critical defects.
- No current project containers are running; Docker Desktop may be stopped.
- FreeBuff Desktop 0.0.53 is installed, but no `freebuff` CLI is on `PATH`.
- Node 22.23.1 and npm 10.9.8 are installed.
- Codex 0.144.1 and Claude Code 2.1.201 are available as optional independent reviewers; primary implementation workers must be FreeBuff as requested.
- Native `tmux` is unavailable. If FreeBuff lacks a non-interactive mode, use a tracked Windows PTY/background process through Hermes rather than pretending tmux exists.
- Code Bridge is a workflow plugin/skill, not a built-in FreeBuff adapter. It supports FreeBuff through its generic terminal-CLI contract after the official CLI is installed and verified.
- FreeBuff's published package states that prompts, messages, code, files, and repository data are sent to the service; some models/features may permit retention or training, and prompt/message processing may personalize ads. Obtain explicit user consent before dispatching repository content.
- FreeBuff is advertised as free, but the published package documents premium-session limits and six one-hour sessions per day in limited mode. Do not design unbounded loops or assume unlimited availability.
- Never send `.env`, credentials, local database contents, DICOM files, real PHI, personal records, or hidden session stores to FreeBuff.
- All application data and test fixtures remain conspicuously synthetic.
- No image interpretation, diagnosis, clinical prioritization, medical advice, DICOM deletion, pixel modification, identity-tag modification, or patient merging.
- No worker may commit to `main`, push, deploy, or bypass approval/sandbox prompts.
- The final commit or push requires a separate explicit user instruction after all gates pass.

## 2. Orchestration Topology

```text
User
  -> Hermes lead/orchestrator
       -> Code Bridge routing and evidence protocol
            -> FreeBuff discovery/research agents (read-only, parallel)
            -> FreeBuff implementation agents (isolated worktrees)
            -> FreeBuff review agents (fresh sessions, read-only)
       -> Hermes verifies diffs, tests, artifacts, migrations, and live smoke
       -> User approves final commit/push
```

### Worker roles

1. **PACS Safety Worker** — transfer finalization, incident persistence, reconciliation incidents, recovery reachability.
2. **Imaging/Reporting Worker** — identity-safe worklist linking, report locking/versioning, correction state, viewer/tag limits.
3. **Frontend Workflow Worker** — selected-study safety, refresh propagation, corrections, RBAC, strict schemas, accessibility.
4. **Documentation/Determinism Worker** — phase/API/data/safety documentation, date-stable tests, formatting.
5. **Fresh Reviewers** — one reviewer per implementation branch, then a final three-way read-only review.

### File ownership during parallel work

- PACS worker owns `backend/app/pacs/transfer.py`, `backend/app/pacs/finalization.py`, selected incident recovery files, PACS workers, and their tests.
- Imaging worker owns `backend/app/imaging/**`, PACS read-boundary code only when assigned, migrations, and imaging/report tests.
- Frontend worker owns `frontend/app/**`, `frontend/features/pacs/**`, and corresponding frontend tests.
- Documentation worker starts only after code branches are integrated to avoid documenting obsolete interfaces.
- If two tasks need the same file, they run sequentially. Hermes never edits a worktree while a FreeBuff worker is active in it.

## 3. Definition of Done for the First Commit-Ready Checkpoint

- Every reproduced blocker has a failing regression test observed before implementation.
- Identity mismatches fail safely and never link or transfer the wrong study.
- Every external transfer outcome has durable incident/audit/recovery evidence.
- Reconciliation mismatches create classified human-review incidents.
- `FINALIZATION_PENDING` and incident-outbox rows have reachable, bounded recovery paths.
- Reopened incidents require a fresh proposal/decision; stale approvals cannot authorize or block the new cycle.
- Concurrent report writes/finalization use PostgreSQL locks or explicit version checks and return safe `409` conflicts.
- Blank/whitespace-only reports and correction reasons are rejected.
- Correction state and authored correction text survive synchronization and browser workflows.
- Fresh PACS inventory synchronization populates and refreshes the primary worklist.
- Orthanc tag/series/preview reads enforce the synthetic boundary, explicit allowlists/bounds, and no-store behavior.
- Frontend roles, keyboard access, strict schemas, report visibility, and refresh behavior match backend policy.
- Canonical architecture, API, data, safety, implementation, phase, README, and handoff docs agree.
- Ruff format/check, mypy, backend tests, Prettier, frontend tests/typecheck/lint/build all pass.
- Alembic upgrades a fresh PostgreSQL database and an existing `0008` database to `0016`/the final head.
- PostgreSQL concurrency tests and connected synthetic Orthanc smoke pass.
- Secret/PHI/artifact/prohibited-operation scans pass.
- Final independent FreeBuff review reports no blocker or high-severity correctness/safety issue.

---

## Phase 0 — Install and Prove the Orchestration Layer

### Task 1: Approve FreeBuff privacy and execution boundaries

**Objective:** Obtain explicit informed consent before any repository content is sent to FreeBuff.

**Files:** None.

**Step 1: Present the verified data-use facts**

State that FreeBuff may process prompts, code, files, and repository data for service delivery and ad personalization, and that some model/feature disclosures may permit training/retention.

**Step 2: Present the repository-safe scope**

- Public/synthetic source only.
- Never read or transmit `.env`, credentials, ignored databases, DICOM files, personal files, or session stores.
- No real PHI.
- Maximum three workers at a time.
- No approval bypass, `--yolo`, commit, push, deploy, or destructive commands.

**Step 3: Ask for explicit consent**

Do not install or dispatch FreeBuff until the user explicitly accepts this processing and scope.

**Expected:** User explicitly authorizes FreeBuff processing for this synthetic/public repository.

### Task 2: Install and verify Hermes Code Bridge

**Objective:** Install the reviewed plugin revision and prove `/code-bridge` is registered.

**Files:** Hermes profile plugin directory only; no project files.

**Step 1: Re-read upstream revision before installation**

Run:

```bash
git ls-remote https://github.com/xuyang-liu16/hermes-code-bridge.git refs/heads/main
```

Expected: `69f97ab148282966979123bb466105bcb2a3bbc4`, or stop and review any newer revision before installing.

**Step 2: Install and enable**

Run:

```bash
hermes plugins install https://github.com/xuyang-liu16/hermes-code-bridge --enable
hermes plugins list
```

Expected: `hermes-code-bridge` appears enabled.

**Step 3: Verify installed files against the reviewed revision**

Compare installed `plugin.yaml`, `__init__.py`, and `skills/hermes-code-bridge/SKILL.md` hashes/content with the pinned GitHub revision. Stop on mismatch.

**Step 4: Restart only the required Hermes surface**

- Desktop session: start a fresh Hermes session/application if command registration is not hot-loaded.
- Gateway: run `hermes gateway restart` only if the gateway is actually in use.

**Step 5: Verify the command read-only**

Invoke:

```text
/code-bridge Identify installed coding CLIs only. Do not launch an agent or modify files.
```

Expected: Code Bridge identifies its workflow and reports installed CLI discovery without editing the repository.

### Task 3: Install the official FreeBuff CLI separately from Desktop

**Objective:** Install a pinned, documented CLI that Code Bridge can actually invoke.

**Files:** npm global package area only; no project files.

**Step 1: Reconfirm package metadata**

Run:

```bash
npm view freebuff@0.0.149 version bin engines dist.integrity --json
```

Expected: version `0.0.149`, binary `freebuff`, Node requirement compatible with Node 22.

**Step 2: Install the pinned CLI**

Run:

```bash
npm install -g freebuff@0.0.149
```

**Step 3: Verify executable resolution**

Run:

```bash
command -v freebuff
where.exe freebuff.cmd
freebuff --help
```

Expected: a real FreeBuff CLI path and documented usage. If `--help` opens a GUI or blocks, stop and use a tracked PTY discovery run.

**Step 4: Record supported invocation modes**

Determine from the installed version's help whether it supports:

- a non-interactive prompt/print flag;
- an explicit working-directory flag;
- session list/resume identifiers;
- structured/JSON output;
- read-only or approval modes.

Do not invent flags. Save the verified command recipe in the run log used by Hermes Code Bridge.

### Task 4: Authenticate FreeBuff and prove a harmless smoke task

**Objective:** Verify that FreeBuff can be driven and monitored without touching the project.

**Files:** Temporary synthetic smoke directory only.

**Step 1: Create an isolated scratch repository**

Use a directory under `C:/Users/abhin/AppData/Local/Temp/freebuff-bridge-smoke`; initialize Git and add one synthetic text file.

**Step 2: Complete any human login/account step**

If FreeBuff presents a login wall, stop and ask the user to authenticate. Never guess credentials or inspect private token stores.

**Step 3: Dispatch a read-only prompt through Code Bridge**

Prompt:

```text
Use the installed FreeBuff CLI in the supplied scratch repository. Read-only. Report the repository root, tracked filename, and git status. Do not edit files, install dependencies, or access parent directories.
```

Use a non-interactive mode if verified. Otherwise use `terminal(background=true, pty=true, notify_on_complete=true)` and tracked `process` input/log operations.

**Step 4: Verify evidence independently**

Run `git status --short`, inspect the scratch file, and confirm no changes. Capture the exact FreeBuff command, exit code, and raw output.

**Step 5: Establish the adapter decision**

- If FreeBuff supports reliable CLI automation: proceed.
- If only interactive PTY works: proceed with one tracked PTY per worker, no parallel prompts in one session.
- If neither works: stop. Do not automate FreeBuff Desktop private internals; use Codex/Claude only if the user authorizes a fallback.

---

## Phase 1 — Preserve and Isolate the Current Dirty Work

### Task 5: Create a recoverable snapshot outside the repository

**Objective:** Preserve the exact 70-path dirty state before any agent changes.

**Files:** Create outside the repo under `C:/Users/abhin/AppData/Local/hermes/agent-snapshots/radiology-operations-copilot/<timestamp>/`.

**Step 1: Re-run safety scans**

Scan changed/untracked paths for `.env`, keys, credentials, databases, DICOM, archives, caches, and likely PHI. Stop on any match requiring human review.

**Step 2: Save tracked changes**

```bash
git diff --binary > <SNAPSHOT_DIR>/tracked.patch
git status --short --branch > <SNAPSHOT_DIR>/status.txt
git rev-parse HEAD > <SNAPSHOT_DIR>/head.txt
```

**Step 3: Archive only Git-visible untracked files**

Build the archive from `git ls-files --others --exclude-standard`; never include ignored `.env`, databases, caches, or Docker volumes.

**Step 4: Hash and verify**

```bash
sha256sum <SNAPSHOT_DIR>/tracked.patch <SNAPSHOT_DIR>/untracked.tar.gz > <SNAPSHOT_DIR>/SHA256SUMS
sha256sum -c <SNAPSHOT_DIR>/SHA256SUMS
```

Expected: all snapshot hashes pass.

### Task 6: Create a local WIP base and isolated worktrees

**Objective:** Enable parallel agents without sharing the dirty working tree.

**Files:** Git metadata and sibling worktree directories only.

**Precondition:** Ask the user to confirm a **local-only WIP checkpoint commit** containing known defects. Never push it.

**Step 1: Create the WIP branch**

```bash
git switch -c agent/pivot-wip
```

**Step 2: Stage only reviewed project paths**

Use explicit path groups, then inspect `git diff --cached --stat` and `git diff --cached --check`. Never stage `.env`, snapshots, databases, DICOM, caches, or agent logs.

**Step 3: Commit the local WIP checkpoint**

```bash
git commit -m "wip: checkpoint imaging workspace pivot for isolated repair"
```

**Step 4: Create isolated worker branches/worktrees**

```bash
git branch agent/pacs-safety

git branch agent/imaging-reporting

git branch agent/frontend-workspace

git worktree add C:/Users/abhin/radiology-copilot-worktrees/pacs-safety agent/pacs-safety

git worktree add C:/Users/abhin/radiology-copilot-worktrees/imaging-reporting agent/imaging-reporting

git worktree add C:/Users/abhin/radiology-copilot-worktrees/frontend-workspace agent/frontend-workspace
```

**Step 5: Verify isolation**

Each worktree must report its expected branch and a clean status before dispatch.

---

## Phase 2 — Read-Only Multi-Agent Design Wave

### Task 7: Dispatch three parallel FreeBuff design reviewers

**Objective:** Have independent agents validate the remediation design before any implementation.

**Files:** None; read-only.

**Prompt contract for every reviewer:**

```markdown
You are a read-only safety reviewer for the synthetic Radiology Operations Copilot.
Working directory: <WORKTREE>
Read AGENTS.md first.
Do not modify files, install dependencies, commit, push, inspect .env, or access parent directories.
Treat all application data as synthetic. Do not propose image interpretation, diagnosis, clinical prioritization, DICOM deletion/modification, or patient merging.
For each conclusion provide file paths, line references, a minimal failing-test design, and the smallest safe implementation approach.
Report blockers, assumptions, verification commands, and unresolved risks.
```

**Reviewer A scope:** transfer transaction recovery, incident persistence, reconciliation mismatches, finalization recovery, repeated failures, outbox concurrency.

**Reviewer B scope:** worklist identity matching, report concurrency, blank content, corrections, synchronization, tag/series/preview bounds.

**Reviewer C scope:** selected-study transfer, parent refresh, FreeBuff-safe frontend changes, RBAC, strict schemas, accessibility, documentation consistency.

**Verification:** Hermes compares each report with source and existing reproductions. Worker self-reports are leads, not proof.

---

## Phase 3 — PACS and Incident Safety Repairs

### Task 8: Make transfer failure persistence transaction-safe

**Objective:** Guarantee durable outcome and incident recovery evidence after one external adapter call, even when incident or audit persistence fails.

**Files:**
- Modify: `backend/app/pacs/transfer.py`
- Modify: `backend/app/incidents/outbox.py`
- Modify: `backend/app/incidents/recovery.py`
- Test: `backend/tests/test_pacs_incident_persistence.py`
- Test: `backend/tests/test_incident_approval_workflow.py`

**Step 1: RED — add the audit-failure regression test**

Write a test that performs one failed adapter call, forces final `pacs.transfer.attempted` audit failure, and asserts that durable recovery evidence exists after rollback.

**Step 2: Verify RED**

```bash
cd backend
env -u PYTHONPATH uv run pytest tests/test_pacs_incident_persistence.py -k audit_failure -v
```

Expected: FAIL with zero incident/outbox evidence.

**Step 3: RED — add the poisoned-session regression test**

Force a SQLAlchemy flush/integrity failure during incident persistence and assert the transfer does not remain `transferring` and a fresh transaction records recovery evidence.

**Step 4: Verify RED**

Expected: FAIL with `PendingRollbackError` or stuck transfer state.

**Step 5: GREEN — implement fresh-transaction recovery**

Rollback failed units before enqueueing; re-query immutable transfer/attempt facts; persist outcome and recovery evidence in an independent bounded transaction. Ensure no second adapter call occurs.

**Step 6: Verify GREEN**

Run the two focused tests and existing transfer/incident tests. Expected: PASS and adapter call count exactly one.

**Step 7: Commit worker branch**

```bash
git add backend/app/pacs/transfer.py backend/app/incidents/outbox.py backend/app/incidents/recovery.py backend/tests/test_pacs_incident_persistence.py backend/tests/test_incident_approval_workflow.py
git commit -m "fix: preserve incident evidence after transfer failures"
```

### Task 9: Create incidents for reconciliation mismatches

**Objective:** Route identity/count reconciliation failures into deterministic human-review incidents.

**Files:**
- Modify: `backend/app/pacs/transfer.py`
- Modify: `backend/app/incidents/classifier.py`
- Test: `backend/tests/test_pacs_incident_persistence.py`
- Test: `backend/tests/test_incident_classifier.py`

**Step 1: RED**

Add separate tests for patient/accession/UID mismatch and count mismatch. Assert `RECONCILIATION_FAILED`, one classified incident, audit evidence, and no automated action.

**Step 2: Verify RED**

Run focused tests; expected failure because no incident is created.

**Step 3: GREEN**

Invoke the deterministic classifier and incident service from the reconciliation failure transaction. Preserve immutable reconciliation evidence and fail closed if incident persistence needs the outbox.

**Step 4: Verify GREEN**

Run reconciliation, classifier, and persistence tests. Expected: PASS, exactly one incident per transfer, no adapter retry.

**Step 5: Commit**

```bash
git commit -am "fix: route reconciliation mismatches to incident review"
```

### Task 10: Make finalization recovery reachable and bounded

**Objective:** Ensure `FINALIZATION_PENDING` transfers have a protected, idempotent recovery mechanism.

**Files:**
- Modify: `backend/app/pacs/finalization.py`
- Modify: `backend/app/pacs/router.py` or `backend/app/workers/pacs_tasks.py`—choose one explicit operator/worker path, not both unless required.
- Modify: `backend/app/pacs/schemas.py`
- Test: appropriate PACS API/worker test under `backend/tests/`

**Step 1: RED**

Add tests proving a pending transfer can be recovered once, duplicate recovery is idempotent, original external error evidence is preserved, and no PACS adapter is called.

**Step 2: Verify RED**

Expected: FAIL because no caller exists.

**Step 3: GREEN**

Expose one bounded authenticated recovery path, enforce role and status, preserve original error code separately from recovery error, append audit evidence, and never perform the transfer again.

**Step 4: Verify GREEN**

Run focused API/worker tests. Expected: PASS; adapter call count zero.

**Step 5: Commit**

```bash
git commit -am "fix: expose bounded transfer finalization recovery"
```

### Task 11: Repair incident lifecycle and outbox concurrency

**Objective:** Require fresh approval after repeated failure and prevent duplicate outbox processing.

**Files:**
- Modify: `backend/app/incidents/service.py`
- Modify: `backend/app/incidents/workflow.py`
- Modify: `backend/app/incidents/recovery.py`
- Modify: incident models/migration only if a cycle/generation field is required.
- Test: `backend/tests/test_incident_approval_workflow.py`

**Step 1: RED — repeated failure**

Create/approve a proposal, record another failure, and assert the old approval is historical while a new proposal can be created for the new incident cycle.

**Step 2: RED — concurrent drain**

Use PostgreSQL sessions to run two drains against the same rows and assert each outbox row and audit is processed exactly once.

**Step 3: RED — classification fidelity**

Enqueue an HTTP 503 failure and assert recovery preserves `connectivity`, including `http_status` evidence.

**Step 4: GREEN**

Introduce the smallest cycle/version invariant; recheck outbox status after each lock boundary or process one locked row per transaction; preserve all classifier inputs.

**Step 5: Verify**

Run focused SQLite tests plus PostgreSQL concurrency tests. Expected: PASS with deterministic classification and no duplicate counts/audits.

**Step 6: Commit**

```bash
git commit -am "fix: version incident decisions and serialize outbox recovery"
```

**Step 7: Fresh FreeBuff review**

Dispatch a new read-only FreeBuff session against `agent/pacs-safety`. Require blocker/high/medium findings, exact diff review, and test gaps. Fix any blocker/high via a new TDD cycle before integration.

---

## Phase 4 — Imaging, Reporting, and Read-Boundary Repairs

### Task 12: Enforce identity-safe worklist matching

**Objective:** Never associate a PACS study to a scheduled patient using accession alone.

**Files:**
- Modify: `backend/app/imaging/service.py`
- Test: `backend/tests/test_imaging_workspace.py`

**Step 1: RED**

Add a test with two synthetic patients and colliding accession values. Assert no mismatched association and a safe exception/unmatched work item rather than an automatic link.

**Step 2: Verify RED**

Expected: FAIL because the newer wrong-patient study is selected.

**Step 3: GREEN**

Match on accession plus normalized synthetic patient identity and required study UID/node criteria. On ambiguity or mismatch, preserve separate work items and human-visible evidence; do not merge.

**Step 4: Verify GREEN**

Run identity, standalone PACS, duplicate-node, and timeline tests.

**Step 5: Commit**

```bash
git commit -am "fix: require patient identity for worklist projection"
```

### Task 13: Add report locking, version conflicts, and content validation

**Objective:** Guarantee one finalization per workflow version and reject blank authored reports.

**Files:**
- Modify: `backend/app/imaging/reporting.py`
- Modify: `backend/app/imaging/schemas.py`
- Modify: `backend/app/imaging/router.py`
- Modify: `backend/app/imaging/models.py`
- Modify/create Alembic revision only if a database version column/check is required.
- Test: `backend/tests/test_phase3_reporting.py`

**Step 1: RED — stale concurrent finalization**

Use two PostgreSQL sessions that load the same draft. First finalize succeeds; second must receive a domain conflict mapped to HTTP `409`, with only one final version.

**Step 2: RED — draft/correction races**

Add expected-version conflict tests for draft save and correction creation.

**Step 3: RED — blank input**

Assert blank/whitespace-only indication, findings, impression, and correction reason are rejected by schema/domain validation.

**Step 4: GREEN**

Lock the report row or use an explicit expected/current version conditional update. Generate the next immutable version under the lock, map conflicts to `409`, and normalize/validate authored text.

**Step 5: Verify**

Run service tests, API tests, and live PostgreSQL concurrency tests.

**Step 6: Commit**

```bash
git commit -am "fix: serialize report versioning and reject blank reports"
```

### Task 14: Preserve correction state and populate the worklist automatically

**Objective:** Keep report/worklist status coherent and make inventory synchronization update the primary worklist.

**Files:**
- Modify: `backend/app/imaging/service.py`
- Modify: `backend/app/imaging/router.py`
- Modify: `backend/app/pacs/router.py` or the inventory orchestration service.
- Test: `backend/tests/test_imaging_workspace.py`
- Test: appropriate API test.

**Step 1: RED — correction state**

Assert `CORRECTION_PENDING` remains correction-pending after worklist synchronization.

**Step 2: RED — fresh inventory flow**

After PACS inventory sync, assert the corresponding worklist projection exists without a manual undocumented call.

**Step 3: GREEN**

Preserve all valid report workflow states and invoke projection synchronization from one documented post-inventory transaction boundary. Audit the mutation.

**Step 4: Verify**

Run worklist, inventory, API authorization, and audit tests.

**Step 5: Commit**

```bash
git commit -am "fix: synchronize imaging worklist after inventory refresh"
```

### Task 15: Bound and filter Orthanc metadata/preview reads

**Objective:** Enforce synthetic-only, allowlisted, resource-bounded Orthanc read surfaces.

**Files:**
- Modify: `backend/app/pacs/orthanc.py`
- Modify: `backend/app/pacs/router.py`
- Modify: `backend/app/pacs/schemas.py`
- Modify: `backend/app/config.py` only for explicit preview/tag limits.
- Test: `backend/tests/test_phase2_viewer.py`
- Test: relevant PACS API tests.

**Step 1: RED — synthetic boundary**

Assert tag/series routes reject a persisted study without current synthetic attestation.

**Step 2: RED — allowlist**

Return an unexpected Orthanc tag and assert it is omitted/rejected rather than passed through.

**Step 3: RED — preview size**

Return an oversized rendered preview and assert bounded failure without buffering/persisting unbounded content.

**Step 4: RED — request count bounds**

Assert series/instance enumeration respects configured caps and reports truncation/failure safely.

**Step 5: GREEN**

Use explicit metadata allowlists, synthetic checks at every live read, streaming/size-limited preview handling, bounded series/instance counts, redacted errors, and `Cache-Control: no-store`.

**Step 6: Verify**

Run adapter and API tests for RBAC, ownership, headers, MIME types, limits, and no-store behavior.

**Step 7: Commit**

```bash
git commit -am "fix: enforce bounded synthetic Orthanc read surfaces"
```

**Step 8: Fresh FreeBuff review**

Dispatch a new read-only FreeBuff reviewer against `agent/imaging-reporting`; resolve all blocker/high findings with TDD.

---

## Phase 5 — Frontend Workflow Repairs

### Task 16: Prevent wrong-study transfer and stale embedded data

**Objective:** Ensure every transfer action uses the currently selected study ID and refreshes shared state.

**Files:**
- Modify: `frontend/features/pacs/pacs-operations-workspace.tsx`
- Modify: `frontend/app/pacs-ops/page.tsx`
- Test: `frontend/tests/pacs-operations-workspace.test.tsx`
- Test: `frontend/tests/imaging-workspace.test.tsx`

**Step 1: RED — selected study ID**

Render multiple studies with a selected study and assert the submitted form contains that study's UUID, never its accession or the first option.

**Step 2: RED — refresh propagation**

Perform inventory sync/health reload and assert parent worklist/node/study state updates without page reload.

**Step 3: GREEN**

Use study UUID consistently and provide controlled callbacks or a single parent-owned refresh function. Remove dual internal/external sources of truth.

**Step 4: Verify**

```bash
cd frontend
npx --yes pnpm@10.14.0 test -- pacs-operations-workspace imaging-workspace
```

Expected: focused tests pass.

**Step 5: Commit**

```bash
git commit -am "fix: bind PACS actions to the selected study"
```

### Task 17: Make correction authoring coherent end to end

**Objective:** Allow users to author corrected text before creating/finalizing an immutable correction version.

**Files:**
- Modify: `frontend/features/pacs/report-editor.tsx`
- Modify: backend report endpoint/schema only if the chosen API contract changes.
- Test: `frontend/tests/report-editor.test.tsx`
- Test: `backend/tests/test_phase3_reporting.py`

**Step 1: RED**

Finalize a report in the component test, enter correction mode, edit findings/impression, provide a reason, save/create correction, and assert the corrected text—not the original—is sent and displayed.

**Step 2: Verify RED**

Expected: FAIL because fields are disabled before creation and later edits are ignored.

**Step 3: GREEN**

Use an explicit correction-edit mode. Submit corrected content plus reason atomically to the correction endpoint, then allow finalization of exactly that persisted version. Do not route correction edits through the draft endpoint unless the backend state machine explicitly supports it.

**Step 4: Verify**

Run frontend correction tests and backend report state-machine tests.

**Step 5: Commit**

```bash
git commit -am "fix: support authored report corrections"
```

### Task 18: Align RBAC, strict schemas, report visibility, and accessibility

**Objective:** Make the primary workflow usable and consistent for every documented role.

**Files:**
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/pacs-ops/page.tsx`
- Modify: `frontend/features/pacs/incident-review-panel.tsx`
- Modify: `frontend/features/pacs/imaging-worklist.tsx`
- Modify: `frontend/features/pacs/report-editor.tsx`
- Modify: `frontend/features/pacs/study-detail.tsx`
- Test: corresponding files under `frontend/tests/`.

**Step 1: RED — system administrator**

Assert login routing and page permissions allow `system_admin` to reach incident approval/outbox controls without receiving an endless loading state.

**Step 2: RED — strict response validation**

Feed unexpected fields or malformed outbox payloads and assert strict Zod parsing fails safely; remove `.passthrough()` and unchecked casts.

**Step 3: RED — keyboard worklist**

Tab to a worklist action and activate it with Enter/Space. Assert selected study changes and accessible name is present.

**Step 4: RED — auditor report content**

Assert a read-only auditor sees authored indication, findings, impression, author, version, date, and correction reason without edit controls.

**Step 5: RED — report status refresh**

Save/finalize/correct and assert the parent worklist status updates immediately.

**Step 6: GREEN**

Centralize the role matrix, strict schemas, accessible row/button controls, report-read rendering, and a parent refresh callback. Remove contradictory “reporting planned” text.

**Step 7: Verify**

Run all frontend tests, typecheck, lint, and accessibility-focused component tests.

**Step 8: Commit**

```bash
git commit -am "fix: align imaging workspace roles and accessible workflows"
```

**Step 9: Fresh FreeBuff review**

Dispatch a new read-only FreeBuff reviewer against `agent/frontend-workspace`; resolve all blocker/high findings with TDD.

---

## Phase 6 — Integrate, Stabilize, and Document

### Task 19: Integrate reviewed worker branches

**Objective:** Combine only independently reviewed commits into one integration branch.

**Files:** Git metadata only initially.

**Step 1: Create integration worktree from the WIP checkpoint**

```bash
git branch agent/integration agent/pivot-wip
git worktree add C:/Users/abhin/radiology-copilot-worktrees/integration agent/integration
```

**Step 2: Cherry-pick PACS commits**

Cherry-pick in dependency order; inspect each diff and run PACS/incident tests after each commit.

**Step 3: Cherry-pick imaging/reporting commits**

Resolve overlap only after reading both versions; never accept an entire side blindly. Run imaging/report tests.

**Step 4: Cherry-pick frontend commits**

Run focused component tests and typecheck.

**Step 5: Verify no worker remains active**

Do not modify or remove worktrees until every tracked process is complete and logs are captured.

### Task 20: Fix date-sensitive scheduling fixtures using TDD

**Objective:** Make scheduling tests deterministic and non-expiring without weakening past-slot policy.

**Files:**
- Modify: the five failing scheduling test fixtures under `backend/tests/`.
- Modify production clock injection only if necessary and covered by tests.

**Step 1: Confirm baseline failures**

Run the five failing tests and verify they fail because August 4–6, 2026 slots are now past.

**Step 2: RED**

Add/adjust fixture helpers to produce clearly future synthetic dates relative to the test clock while retaining explicit past-slot denial tests.

**Step 3: GREEN**

Use one deterministic test-time helper or injected clock; do not change the production rule that rejects past slots.

**Step 4: Verify**

Run focused scheduling tests, then the full backend suite.

**Step 5: Commit**

```bash
git commit -am "test: make scheduling fixtures time-stable"
```

### Task 21: Apply formatters and resolve static checks

**Objective:** Eliminate the known Ruff/Prettier failures without unrelated refactors.

**Files:** The 15 Ruff and 16 Prettier paths already reported, plus only files touched by fixes.

**Step 1: Run formatters**

```bash
cd backend
env -u PYTHONPATH uv run ruff format app tests alembic
cd ../frontend
npx --yes pnpm@10.14.0 exec prettier --write .
```

**Step 2: Inspect formatting diff**

Ensure only mechanical changes occurred and no CRLF/binary/secret artifacts were introduced.

**Step 3: Run static gates**

```bash
cd backend
env -u PYTHONPATH uv run ruff format --check app tests alembic
env -u PYTHONPATH uv run ruff check app tests alembic
env -u PYTHONPATH uv run mypy app
cd ../frontend
npx --yes pnpm@10.14.0 exec prettier --check .
npx --yes pnpm@10.14.0 typecheck
npx --yes pnpm@10.14.0 lint
```

Expected: all pass with no warnings accepted silently; decide explicitly whether the synthetic blob `<img>` warning is justified or fix it.

**Step 4: Commit**

```bash
git commit -am "style: format imaging workspace checkpoint"
```

### Task 22: Reconcile canonical product documentation

**Objective:** Make every document describe one coherent end goal, implemented checkpoint, and safety boundary.

**Files:**
- Modify: `README.md`
- Modify: `docs/imaging-workspace-pivot.md`
- Modify: `docs/08-data-model.md`
- Modify: `docs/09-api-contract.md`
- Modify: `docs/10-risk-and-safety-analysis.md`
- Modify: `docs/15-implementation-plan.md`
- Modify: `docs/phase-reports/phase-3.md`
- Modify: `docs/phase-reports/phase-4.md`
- Modify: `handoff.md`
- Consider creating a new A–D phase report instead of overwriting historical numeric Phase 3 evidence.

**Step 1: Preserve historical evidence**

Restore or relocate the original PACS Phase 3 report rather than erasing it. Document the A–D product slices separately from numeric infrastructure phases.

**Step 2: Document actual tables and migrations**

Advance the data model through the final Alembic head, including worklist, reports/versions, finalization recovery, incidents, outbox, proposals, decisions, constraints, and mutability.

**Step 3: Document actual APIs and role matrix**

Add all `/imaging` and `/incidents` routes, request/response schemas, synthetic headers, error codes, idempotency, limits, and authorization roles.

**Step 4: Document safety and limitations**

State what is implemented, what is not, privacy boundaries, no diagnosis/image interpretation, no autonomous retry, and FreeBuff development-agent use as an external code-processing tool—not an application dependency.

**Step 5: Verify documentation claims against code/tests**

Search every “planned,” “unavailable,” “implemented,” migration-head, endpoint-count, and phase-status statement. No contradictory claim remains.

**Step 6: Commit**

```bash
git commit -am "docs: align imaging workspace architecture and safety checkpoint"
```

---

## Phase 7 — Real Verification and Final Review

### Task 23: Prove migrations and concurrency on PostgreSQL

**Objective:** Validate behavior that SQLite cannot prove.

**Files:** Tests/config only if failures expose real defects.

**Step 1: Start a temporary PostgreSQL test instance**

Use an isolated temporary container and cleanup trap; do not reuse or delete project volumes.

**Step 2: Test a fresh migration**

```bash
uv run alembic upgrade head
uv run alembic current
```

Expected: final single head.

**Step 3: Test upgrade from the previous committed head**

Create schema at `0008_transfer_dispatch_outbox`, then upgrade to head. Verify expected tables, indexes, constraints, and preserved data.

**Step 4: Test downgrade/re-upgrade where supported**

Verify downgrade behavior or explicitly document irreversible migrations with rationale.

**Step 5: Run PostgreSQL-specific tests**

Run report finalization concurrency, incident outbox locking, proposal separation, transfer recovery, and booking row-lock/version tests.

**Step 6: Cleanup**

Remove the temporary container and verify no test process remains.

### Task 24: Run the full deterministic quality gate

**Objective:** Produce one decisive clean verification pass.

**Backend:**

```bash
cd backend
env -u PYTHONPATH uv run ruff format --check app tests alembic
env -u PYTHONPATH uv run ruff check app tests alembic
env -u PYTHONPATH uv run mypy app
env -u PYTHONPATH uv run pytest -q
```

**Frontend:**

```bash
cd frontend
npx --yes pnpm@10.14.0 exec prettier --check .
npx --yes pnpm@10.14.0 test
npx --yes pnpm@10.14.0 typecheck
npx --yes pnpm@10.14.0 lint
npx --yes pnpm@10.14.0 build
```

**Compose:**

```bash
docker compose config --quiet
```

Expected: every command exits zero; record exact counts and raw logs.

### Task 25: Run connected synthetic Orthanc and browser smoke

**Objective:** Prove the complete local workflow without real PHI or destructive operations.

**Step 1: Start the stack**

```bash
docker compose up -d --build
```

Use the existing ignored local `.env`; never print it.

**Step 2: Run connected integration gate**

```bash
make test-integration
```

Expected: synthetic-only source/destination inventories, bounded transfer, positive reconciliation, no destructive operation.

**Step 3: Run authenticated browser smoke**

Verify:

- scheduler workflow remains available;
- imaging worklist populates after inventory sync;
- selected-study transfer ID remains correct;
- preview and prior comparison are synthetic/no-store;
- report draft/final/correction works;
- auditor can read but not write;
- system administrator reaches incident decisions;
- reconciliation mismatch becomes an incident;
- approval does not execute a retry;
- keyboard navigation opens worklist items;
- footer/README show the synthetic-prototype disclaimer.

**Step 4: Preserve evidence**

Store redacted logs and screenshots outside the committed source tree unless project documentation explicitly needs sanitized evidence.

**Step 5: Stop the project stack**

```bash
docker compose down --remove-orphans
```

Do not use `-v`; preserve synthetic volumes unless the user explicitly requests deletion. Verify `docker compose ps --all` is empty.

### Task 26: Run the final three-agent read-only review

**Objective:** Obtain independent spec, safety, and UX approval using fresh FreeBuff sessions.

**Reviewer 1:** backend transaction/concurrency/authorization/audit review.

**Reviewer 2:** frontend workflow/RBAC/accessibility/schema review.

**Reviewer 3:** architecture/docs/synthetic boundary/test-evidence review.

Every prompt must say:

```text
Read-only. Do not edit, commit, push, install, start services, inspect .env, or access parent directories. Review the complete integration diff against AGENTS.md and the end-goal documents. Report blocker/high/medium/low findings with file and line evidence. Treat success claims as unverified until tied to raw test output.
```

Hermes verifies each finding, resolves every blocker/high via a new TDD cycle, and reruns affected/full gates.

### Task 27: Prepare the final commit without pushing

**Objective:** Replace the local WIP history with a clean, reviewable checkpoint only after all gates pass.

**Step 1: Inspect final state**

```bash
git status --short --branch
git diff --stat agent/pivot-wip..HEAD
git diff --check
git log --oneline --decorate --graph -n 30
```

**Step 2: Re-run secret/artifact/PHI/prohibited-operation scans**

Fail on `.env`, secrets, keys, databases, DICOM, pixel data, caches, build artifacts, real-looking patient data, deletion/tag mutation/merge operations, or autonomous retry.

**Step 3: Decide commit structure**

Recommended final logical commits:

1. `fix: harden PACS incident and recovery workflows`
2. `fix: make imaging worklist and reporting deterministic`
3. `fix: align imaging workspace frontend workflows`
4. `test: stabilize full project verification`
5. `docs: align radiology copilot product checkpoint`

Keep the local WIP commit off final `main` history by rebasing/squashing on an integration branch only after explicit user approval.

**Step 4: Ask before committing**

Present changed files, test evidence, migration evidence, connected smoke evidence, independent-review verdict, and remaining limitations. Do not commit or push until explicitly instructed.

---

## Phase 8 — Roadmap from Commit-Ready Pivot to the End Goal

These phases begin only after Task 27 is green and committed. Each is a separate plan/checkpoint with its own TDD, safety review, migrations, docs, and connected tests.

### Milestone 0.2: Controlled share/export

**Goal:** Deliver authored synthetic reports through explicit, auditable, non-production adapters.

**Likely files:**
- New typed sharing/export adapter under `backend/app/imaging/` or a dedicated `backend/app/sharing/` domain.
- New migrations for share intents/outcomes and expiring links.
- MailHog-only delivery adapter.
- PDF renderer that includes the synthetic disclaimer.
- Mock FHIR `DiagnosticReport` serializer/validator.
- Frontend explicit destination/expiry/revoke controls.
- Docs: architecture, API, data, safety, implementation, phase report.

**Acceptance:** allowlisted destinations, expiring tokens stored hashed, idempotency, audit events, no external email, no real EHR, strict FHIR schema, revocation, accessibility, connected MailHog smoke.

### Milestone 0.3: Acquisition and interoperability sandbox

**Goal:** Demonstrate standards-based synthetic integration behind typed adapters.

**Scope:** DICOMweb first; then sandbox-only C-STORE receiver, Modality Worklist, MPPS, and mock EHR adapter if each prior slice is safe and justified.

**Acceptance:** synthetic fixtures only, bounded payloads/timeouts/retries, no destructive operations, no pixel storage in PostgreSQL, strict identity reconciliation, idempotency, audit evidence, adapter contract tests, connected sandbox smoke.

### Milestone 0.4: Operational analytics and governance

**Goal:** Provide auditable operational visibility without clinical inference.

**Scope:** transfer/reconciliation timing, incident aging, worklist throughput, audit explorer, policy administration, retention controls, kill-switch visibility, exportable synthetic evidence.

**Acceptance:** metrics are operational only; no diagnosis, clinical ranking, or performance claims based on real patients; all policy changes versioned and audited.

### Milestone 1.0: Portfolio hardening and UAT

**Goal:** Produce a reproducible demonstration that a reviewer can run safely.

**Scope:** browser E2E, WCAG-oriented accessibility, failure-injection tests, Docker reproducibility, backup/reset instructions, architecture diagrams, demo script, threat model, UAT scenarios, limitation disclosures.

**Acceptance:** one-command setup, deterministic synthetic seed, all gates green, no credentials committed, stack starts/stops cleanly, no false clinical claims, explicit non-production disclaimer everywhere.

---

## Risks and Tradeoffs

1. **FreeBuff privacy:** Source and prompts leave the machine. Mitigation: explicit consent, public/synthetic code only, no `.env`/PHI/session stores, narrow prompts, inspect changed files afterward.
2. **FreeBuff limits:** “Free” does not mean unbounded. Mitigation: max three workers, small tasks, session reuse only when reliably matched, no retry loops, deterministic stop conditions.
3. **Desktop vs CLI:** Desktop is installed but not externally invocable. Mitigation: use official CLI; never reverse-engineer private orchestrator/session databases.
4. **Dirty-tree isolation:** Worktrees require a committed base. Mitigation: external snapshot plus explicit local-only WIP checkpoint, never pushed, later removed from final history.
5. **Parallel conflicts:** PACS/imaging concerns overlap. Mitigation: strict file ownership, dependency ordering, sequential execution for overlapping files, cherry-pick review.
6. **SQLite false confidence:** `FOR UPDATE` and concurrent transactions cannot be proven. Mitigation: mandatory PostgreSQL tests before completion.
7. **Agent self-reporting:** A worker may claim success without artifacts. Mitigation: Hermes verifies real diffs, files, raw tests, migration state, and connected behavior.
8. **Scope expansion:** The end goal is broad. Mitigation: first converge the existing pivot; every later milestone receives a separate explicit plan and approval.
9. **Clinical overreach:** Reporting/viewer language can imply diagnosis. Mitigation: authored-only text, synthetic watermark/disclaimer, no model-generated diagnosis, explicit governance and limitations.
10. **Known bad WIP commit:** Necessary for worktree isolation but unsuitable for final history. Mitigation: local-only branch, clear `wip:` label, verified snapshot, clean rebase/squash before final commit.

## Open Questions Requiring User Decisions Before Execution

1. Do you consent to FreeBuff processing this public/synthetic repository under its published data-use terms, with `.env`, credentials, PHI, DICOM, personal files, and session stores excluded?
2. Do you authorize creation of a local-only `agent/pivot-wip` checkpoint commit so isolated parallel worktrees can be created? It will never be pushed and will be removed from final history.
3. If FreeBuff CLI does not expose reliable non-interactive/PTY automation, should orchestration stop, or may Codex/Claude become fallback workers?
4. Should the final checkpoint use the five logical commits proposed above or one squashed portfolio checkpoint?
5. After a green local checkpoint, should Hermes only prepare the commit, create it, or also push—each requires separate explicit approval.

## Final Plan Review Checklist

- [x] Exact repository and current dirty state captured.
- [x] Code Bridge installation grounded in the upstream repository.
- [x] FreeBuff Desktop/CLI distinction verified.
- [x] FreeBuff privacy and usage-limit caveats included.
- [x] No reliance on unavailable tmux.
- [x] Worktree isolation and recovery snapshot included.
- [x] Every known blocker mapped to a TDD task.
- [x] Exact files and verification commands listed.
- [x] PostgreSQL and connected Orthanc proof required.
- [x] Documentation and historical phase reconciliation included.
- [x] Final independent agent review and human commit gate included.
- [x] Long-term path to the complete product included.
