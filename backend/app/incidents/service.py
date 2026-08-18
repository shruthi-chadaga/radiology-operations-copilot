"""Persistence boundary for deterministic PACS transfer-failure incidents."""

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.incidents.classifier import IncidentClassificationResult
from app.incidents.models import (
    IncidentProposalStatus,
    IncidentRemediationProposal,
    PacsIncident,
    PacsIncidentApprovalState,
    PacsIncidentStatus,
)
from app.incidents.outbox import IncidentPersistenceOutbox
from app.pacs.models import TransferAttempt, TransferJob


def _sanitize_failure_summary(value: str) -> str:
    """Persist only a bounded type/status summary, never raw exception content."""
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]{0,79})(?:: transfer request failed)?$", value)
    return f"{match.group(1)}: transfer request failed" if match else "redacted transfer failure"


def enqueue_incident_persistence(
    session: Session,
    job: TransferJob,
    *,
    error_code: str,
    redacted_error: str,
    http_status: int | None = None,
    evidence: dict[str, object] | None = None,
) -> IncidentPersistenceOutbox:
    """Durably record that incident creation must be retried; never dispatch remediation."""

    evidence_payload = dict(evidence) if evidence else {}
    if http_status is not None and type(http_status) is int:
        evidence_payload["http_status"] = http_status
    existing = session.scalar(
        select(IncidentPersistenceOutbox).where(IncidentPersistenceOutbox.transfer_job_id == job.id)
    )
    if existing is not None:
        existing.status = "pending"
        existing.error_code = error_code[:80]
        existing.redacted_error = _sanitize_failure_summary(redacted_error)[:200]
        if evidence_payload:
            existing.evidence_json = {**existing.evidence_json, **evidence_payload}
        existing.attempt_count += 1
        existing.last_attempt_at = datetime.now(UTC)
        return existing
    outbox = IncidentPersistenceOutbox(
        transfer_job_id=job.id,
        error_code=error_code[:80],
        redacted_error=_sanitize_failure_summary(redacted_error)[:200],
        evidence_json=evidence_payload,
        status="pending",
        attempt_count=1,
        last_attempt_at=datetime.now(UTC),
    )
    try:
        with session.begin_nested():
            session.add(outbox)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(IncidentPersistenceOutbox).where(
                IncidentPersistenceOutbox.transfer_job_id == job.id
            )
        )
        if existing is None:
            raise
        existing.status = "pending"
        existing.attempt_count += 1
        existing.last_attempt_at = datetime.now(UTC)
        return existing
    return outbox


def _latest_attempt_number(session: Session, job: TransferJob) -> int | None:
    return session.scalar(
        select(TransferAttempt.attempt_number)
        .where(TransferAttempt.transfer_job_id == job.id)
        .order_by(TransferAttempt.attempt_number.desc())
        .limit(1)
    )


def _audit_state(
    job: TransferJob,
    classification: IncidentClassificationResult,
    latest_attempt: int | None,
) -> dict[str, object]:
    return {
        "category": classification.category.value,
        "severity": classification.severity.value,
        "rule_code": classification.rule_code,
        "retry_candidate": classification.retry_candidate,
        "confidence": classification.confidence,
        "attempt_number": latest_attempt,
        "error_code": job.last_error_code,
    }


_RECONCILIATION_OUTCOMES = frozenset(
    {"identity_mismatch", "count_mismatch", "missing_or_ambiguous"}
)


def _bound_reconciliation_evidence(
    evidence: dict[str, object] | None,
) -> dict[str, object]:
    """Keep reconciliation evidence to deterministic metadata facts only."""

    if not evidence:
        return {}
    bounded: dict[str, object] = {}
    outcome = evidence.get("reconciliation_outcome")
    if type(outcome) is str and outcome in _RECONCILIATION_OUTCOMES:
        bounded["reconciliation_outcome"] = outcome
    for key in (
        "reconciliation_identifiers_match",
        "reconciliation_instance_counts_match",
    ):
        value = evidence.get(key)
        if value is None or type(value) is bool:
            bounded[key] = value
    for key in (
        "reconciliation_source_match_count",
        "reconciliation_destination_match_count",
        "reconciliation_source_instance_count",
        "reconciliation_destination_instance_count",
    ):
        value = evidence.get(key)
        if type(value) is int and 0 <= value <= 2_147_483_647:
            bounded[key] = value
    return bounded


def _supersede_active_proposals(
    session: Session,
    incident: PacsIncident,
    *,
    actor_id: str,
    job: TransferJob,
    failure_count: int,
    now: datetime,
) -> None:
    proposals = session.scalars(
        select(IncidentRemediationProposal)
        .where(
            IncidentRemediationProposal.incident_id == incident.id,
            IncidentRemediationProposal.status.in_(
                [IncidentProposalStatus.PENDING, IncidentProposalStatus.APPROVED]
            ),
        )
        .with_for_update()
    )
    for proposal in proposals:
        previous_status = proposal.status.value
        proposal.status = IncidentProposalStatus.SUPERSEDED
        proposal.decided_at = now
        append_audit_event(
            session,
            actor=AuditActor("system", actor_id),
            action="pacs.incident.proposal.superseded",
            entity_type="incident_remediation_proposal",
            entity_id=str(proposal.id),
            decision_reason=(
                "New transfer failure evidence invalidated the proposal; historical approval "
                "evidence remains unchanged"
            ),
            correlation_id=job.correlation_id,
            request_id=job.idempotency_key,
            success=True,
            policy_version="pacs-incident-v1",
            before_state={
                "incident_id": str(incident.id),
                "proposal_id": str(proposal.id),
                "status": previous_status,
                "failure_count": failure_count - 1,
            },
            after_state={
                "incident_id": str(incident.id),
                "proposal_id": str(proposal.id),
                "status": proposal.status.value,
                "failure_count": failure_count,
                "execution_authorized": False,
                "approval_is_not_execution": True,
            },
        )


def _update_existing_incident(
    session: Session,
    existing: PacsIncident,
    job: TransferJob,
    classification: IncidentClassificationResult,
    *,
    safe_error: str,
    actor_id: str,
    latest_attempt: int | None,
    reconciliation_evidence: dict[str, object],
) -> PacsIncident:
    now = datetime.now(UTC)
    existing.category = classification.category.value
    existing.severity = classification.severity.value
    existing.retry_candidate = classification.retry_candidate
    existing.requires_human_review = classification.requires_human_review
    existing.confidence = classification.confidence
    existing.rule_code = classification.rule_code
    existing.status = PacsIncidentStatus.OPEN
    existing.approval_state = PacsIncidentApprovalState.PENDING
    existing.resolved_at = None
    existing.resolved_by = None
    existing.resolution = None
    existing.last_failure_count += 1
    _supersede_active_proposals(
        session,
        existing,
        actor_id=actor_id,
        job=job,
        failure_count=existing.last_failure_count,
        now=now,
    )
    existing.updated_at = now
    evidence = dict(existing.evidence_json or {})
    evidence.update(reconciliation_evidence)
    evidence["failure_count"] = existing.last_failure_count
    evidence["latest_attempt_number"] = latest_attempt
    evidence["latest_error_code"] = job.last_error_code
    evidence["latest_redacted_error"] = safe_error
    existing.evidence_json = evidence
    existing.redacted_summary = safe_error
    append_audit_event(
        session,
        actor=AuditActor("system", actor_id),
        action="pacs.incident.updated",
        entity_type="pacs_incident",
        entity_id=str(existing.id),
        decision_reason=(
            "Repeated deterministic transfer failure consolidated into existing incident"
        ),
        correlation_id=job.correlation_id,
        request_id=job.idempotency_key,
        success=True,
        policy_version="pacs-incident-v1",
        after_state={
            **_audit_state(job, classification, latest_attempt),
            "status": existing.status.value,
            "failure_count": existing.last_failure_count,
        },
    )
    return existing


def record_transfer_failure_incident(
    session: Session,
    job: TransferJob,
    classification: IncidentClassificationResult,
    *,
    redacted_error: str,
    actor_id: str,
    evidence: dict[str, object] | None = None,
) -> PacsIncident:
    """Create or update one incident for a transfer failure.

    This function persists evidence only. It never evaluates authorization or starts a retry.
    The caller owns the surrounding transaction and must commit explicitly.
    """

    safe_error = _sanitize_failure_summary(redacted_error)
    latest_attempt = _latest_attempt_number(session, job)
    bounded_evidence = _bound_reconciliation_evidence(evidence)
    existing = session.scalar(
        select(PacsIncident).where(PacsIncident.transfer_job_id == job.id).with_for_update()
    )
    if existing is not None:
        return _update_existing_incident(
            session,
            existing,
            job,
            classification,
            safe_error=safe_error,
            actor_id=actor_id,
            latest_attempt=latest_attempt,
            reconciliation_evidence=bounded_evidence,
        )

    incident = PacsIncident(
        incident_number=f"PACS-INC-{job.id.hex[:12].upper()}",
        transfer_job_id=job.id,
        study_id=job.study_id,
        source_node_id=job.source_node_id,
        destination_node_id=job.destination_node_id,
        category=classification.category.value,
        severity=classification.severity.value,
        status=PacsIncidentStatus.OPEN,
        approval_state=PacsIncidentApprovalState.PENDING,
        retry_candidate=classification.retry_candidate,
        requires_human_review=classification.requires_human_review,
        confidence=classification.confidence,
        rule_code=classification.rule_code,
        evidence_json={
            "failure_count": 1,
            "latest_attempt_number": latest_attempt,
            "latest_error_code": job.last_error_code,
            "latest_redacted_error": safe_error,
            "transfer_status": job.status.value,
            **bounded_evidence,
        },
        redacted_summary=safe_error,
        last_failure_count=1,
    )
    try:
        with session.begin_nested():
            session.add(incident)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(PacsIncident).where(PacsIncident.transfer_job_id == job.id).with_for_update()
        )
        if existing is None:
            raise
        return _update_existing_incident(
            session,
            existing,
            job,
            classification,
            safe_error=safe_error,
            actor_id=actor_id,
            latest_attempt=latest_attempt,
            reconciliation_evidence=bounded_evidence,
        )

    append_audit_event(
        session,
        actor=AuditActor("system", actor_id),
        action="pacs.incident.created",
        entity_type="pacs_incident",
        entity_id=str(incident.id),
        decision_reason="Deterministic transfer failure requires human-controlled incident review",
        correlation_id=job.correlation_id,
        request_id=job.idempotency_key,
        success=True,
        policy_version="pacs-incident-v1",
        after_state={
            **_audit_state(job, classification, latest_attempt),
            "status": incident.status.value,
            "approval_state": incident.approval_state.value,
        },
    )
    return incident
