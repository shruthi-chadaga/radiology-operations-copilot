"""Persistence boundary for deterministic PACS transfer-failure incidents."""

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.incidents.classifier import IncidentClassificationResult
from app.incidents.models import (
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
    evidence: dict[str, object] | None = None,
) -> IncidentPersistenceOutbox:
    """Durably record that incident creation must be retried; never dispatch remediation."""

    existing = session.scalar(
        select(IncidentPersistenceOutbox).where(
            IncidentPersistenceOutbox.transfer_job_id == job.id
        )
    )
    if existing is not None:
        existing.status = "pending"
        existing.error_code = error_code[:80]
        existing.redacted_error = _sanitize_failure_summary(redacted_error)[:200]
        if evidence:
            existing.evidence_json = {**existing.evidence_json, **evidence}
        existing.attempt_count += 1
        existing.last_attempt_at = datetime.now(UTC)
        return existing
    outbox = IncidentPersistenceOutbox(
        transfer_job_id=job.id,
        error_code=error_code[:80],
        redacted_error=_sanitize_failure_summary(redacted_error)[:200],
        evidence_json=evidence or {},
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


def _update_existing_incident(
    session: Session,
    existing: PacsIncident,
    job: TransferJob,
    classification: IncidentClassificationResult,
    *,
    safe_error: str,
    actor_id: str,
    latest_attempt: int | None,
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
    existing.updated_at = now
    evidence = dict(existing.evidence_json)
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
            "Repeated deterministic transfer failure consolidated into existing "
            "incident"
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
) -> PacsIncident:
    """Create or update one incident for a transfer failure.

    This function persists evidence only. It never evaluates authorization or starts a retry.
    The caller owns the surrounding transaction and must commit explicitly.
    """

    safe_error = _sanitize_failure_summary(redacted_error)
    latest_attempt = _latest_attempt_number(session, job)
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
