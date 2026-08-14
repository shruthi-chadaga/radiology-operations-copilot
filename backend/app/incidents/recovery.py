"""Bounded recovery worker for incident-persistence evidence."""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.incidents.classifier import IncidentClassificationInput, classify_incident
from app.incidents.outbox import IncidentPersistenceOutbox
from app.incidents.service import (
    _sanitize_failure_summary,
    record_transfer_failure_incident,
)
from app.pacs.models import TransferJob

MAX_OUTBOX_ATTEMPTS = 5


@dataclass(frozen=True)
class OutboxDrainResult:
    selected: int
    completed: int
    deferred: int
    failed: int


def drain_incident_persistence_outbox(
    session: Session,
    *,
    actor_id: str = "incident-outbox-worker",
    limit: int = 20,
    max_attempts: int = MAX_OUTBOX_ATTEMPTS,
) -> OutboxDrainResult:
    """Persist queued incident evidence without calling adapters or starting retries."""

    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if max_attempts < 1 or max_attempts > MAX_OUTBOX_ATTEMPTS:
        raise ValueError("max_attempts must be between 1 and 5")
    entries = list(
        session.scalars(
            select(IncidentPersistenceOutbox)
            .where(IncidentPersistenceOutbox.status == "pending")
            .order_by(IncidentPersistenceOutbox.created_at, IncidentPersistenceOutbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    completed = 0
    deferred = 0
    failed = 0
    for entry in entries:
        next_attempt = entry.attempt_count + 1
        try:
            entry.attempt_count = next_attempt
            entry.last_attempt_at = datetime.now(UTC)
            job = session.get(TransferJob, entry.transfer_job_id)
            if job is None:
                raise LookupError("transfer evidence not found")
            http_status = entry.evidence_json.get("http_status")
            classification = classify_incident(
                IncidentClassificationInput(
                    domain="pacs",
                    source_entity_type="transfer_job",
                    source_entity_id=str(job.id),
                    error_code=entry.error_code,
                    error_message=entry.redacted_error,
                    transfer_status=job.status.value,
                    http_status=http_status if type(http_status) is int else None,
                )
            )
            record_transfer_failure_incident(
                session,
                job,
                classification,
                redacted_error=entry.redacted_error,
                actor_id=actor_id,
            )
            entry.status = "completed"
            entry.completed_at = datetime.now(UTC)
            entry.last_error = None
            append_audit_event(
                session,
                actor=AuditActor("system", actor_id),
                action="pacs.incident.outbox.completed",
                entity_type="incident_persistence_outbox",
                entity_id=str(entry.id),
                decision_reason="Recovered incident evidence without executing remediation",
                correlation_id=job.correlation_id,
                request_id=job.idempotency_key,
                success=True,
                policy_version="pacs-incident-v1",
                after_state={"status": entry.status, "attempt_count": entry.attempt_count},
            )
            completed += 1
        except Exception as exc:
            session.rollback()
            refreshed = session.get(IncidentPersistenceOutbox, entry.id)
            if refreshed is None:
                failed += 1
                continue
            refreshed.attempt_count = next_attempt
            refreshed.last_attempt_at = datetime.now(UTC)
            refreshed.last_error = _sanitize_failure_summary(str(exc))
            refreshed.status = "failed" if next_attempt >= max_attempts else "pending"
            append_audit_event(
                session,
                actor=AuditActor("system", actor_id),
                action="pacs.incident.outbox.failed",
                entity_type="incident_persistence_outbox",
                entity_id=str(refreshed.id),
                decision_reason=(
                    "Incident evidence recovery did not complete; "
                    "no remediation was executed"
                ),
                correlation_id=f"outbox-{refreshed.id}",
                request_id=f"outbox-{refreshed.id}",
                success=False,
                policy_version="pacs-incident-v1",
                after_state={
                    "status": refreshed.status,
                    "attempt_count": refreshed.attempt_count,
                },
                error_code="INCIDENT_OUTBOX_RECOVERY_FAILED",
                error_message=refreshed.last_error,
            )
            if refreshed.status == "failed":
                failed += 1
            else:
                deferred += 1
        session.commit()
    return OutboxDrainResult(
        selected=len(entries), completed=completed, deferred=deferred, failed=failed
    )
