"""Safe recovery for transfer outcomes whose local finalization was interrupted."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.incidents.classifier import IncidentClassificationInput, classify_incident
from app.incidents.service import record_transfer_failure_incident
from app.pacs.models import TransferAttempt, TransferJob, TransferStatus


class FinalizationRecoveryConflict(RuntimeError):
    pass


def recover_transfer_finalization(
    session: Session,
    transfer_id: uuid.UUID,
    *,
    actor_id: str,
) -> TransferJob:
    """Finalize a recorded external outcome without calling a PACS adapter.

    This operation is deliberately not a retry. It only uses the durable attempt outcome
    already recorded before the finalization failure. If incident or audit persistence fails,
    the transaction is rolled back and the job remains recoverable for another attempt.
    """

    job = session.scalar(
        select(TransferJob).where(TransferJob.id == transfer_id).with_for_update()
    )
    if job is None:
        raise FinalizationRecoveryConflict("Transfer was not found")
    if job.status != TransferStatus.FINALIZATION_PENDING:
        raise FinalizationRecoveryConflict("Transfer is not awaiting finalization recovery")
    attempt = session.scalar(
        select(TransferAttempt)
        .where(TransferAttempt.transfer_job_id == job.id)
        .order_by(TransferAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is None or attempt.outcome not in {"accepted", "failed"}:
        raise FinalizationRecoveryConflict("Transfer has no durable external outcome")

    if attempt.outcome == "accepted":
        job.status = TransferStatus.TRANSFERRED
        job.last_error_code = None
        action = "pacs.transfer.finalization_recovered"
        decision_reason = "Recovered accepted external outcome without issuing another transfer"
    else:
        error_code = job.last_error_code or "UNKNOWN_FAILURE"
        redacted_error = attempt.redacted_error or "redacted transfer failure"
        classification = classify_incident(
            IncidentClassificationInput(
                domain="pacs",
                source_entity_type="transfer_job",
                source_entity_id=str(job.id),
                error_code=error_code,
                error_message=redacted_error,
                transfer_status=TransferStatus.FAILED.value,
            )
        )
        record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error=redacted_error,
            actor_id=actor_id,
        )
        job.status = TransferStatus.FAILED
        action = "pacs.transfer.finalization_recovered"
        decision_reason = "Recovered failed external outcome and persisted its incident"

    attempt.completed_at = attempt.completed_at or datetime.now(UTC)
    append_audit_event(
        session,
        actor=AuditActor("system", actor_id),
        action=action,
        entity_type="transfer_job",
        entity_id=str(job.id),
        decision_reason=decision_reason,
        correlation_id=job.correlation_id,
        request_id=job.idempotency_key,
        success=True,
        policy_version="pacs-incident-v1",
        after_state={"status": job.status.value, "attempt": attempt.attempt_number},
        error_code=job.last_error_code,
    )
    session.commit()
    return job
