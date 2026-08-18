"""Idempotent PACS transfer execution and metadata-only reconciliation."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.incidents.classifier import IncidentClassificationInput, classify_incident
from app.incidents.service import (
    enqueue_incident_persistence,
    record_transfer_failure_incident,
)
from app.pacs.adapter import PacsAdapter
from app.pacs.models import (
    PacsNode,
    PacsStudy,
    ReconciliationResult,
    TransferAttempt,
    TransferDispatch,
    TransferJob,
    TransferStatus,
)


class TransferConflict(RuntimeError):
    pass


class DestinationUnavailable(TransferConflict):
    """Typed adapter outcome for a destination connectivity/rejection failure."""

    pass


@dataclass(frozen=True)
class TransferCreate:
    source_node_id: uuid.UUID
    destination_node_id: uuid.UUID
    study_id: uuid.UUID
    idempotency_key: str
    correlation_id: str
    actor_id: str


def _validate_transfer_topology(source: PacsNode, destination: PacsNode) -> None:
    if (
        not source.active
        or not destination.active
        or source.node_type != "source"
        or destination.node_type != "destination"
        or source.adapter_key != "source"
        or destination.adapter_key != "destination"
    ):
        raise TransferConflict("PACS node topology is not allowlisted")


def create_transfer(session: Session, request: TransferCreate) -> TransferJob:
    existing = session.scalar(
        select(TransferJob).where(TransferJob.idempotency_key == request.idempotency_key)
    )
    if existing is not None:
        if (
            existing.source_node_id != request.source_node_id
            or existing.destination_node_id != request.destination_node_id
            or existing.study_id != request.study_id
        ):
            raise TransferConflict("Idempotency key was reused for a different transfer")
        return existing
    study = session.get(PacsStudy, request.study_id)
    source = session.get(PacsNode, request.source_node_id)
    destination = session.get(PacsNode, request.destination_node_id)
    if study is None or source is None or destination is None:
        raise TransferConflict("Transfer references were not found")
    if study.node_id != source.id or source.id == destination.id:
        raise TransferConflict("Transfer source, destination, and study are inconsistent")
    _validate_transfer_topology(source, destination)
    job = TransferJob(
        source_node_id=source.id,
        destination_node_id=destination.id,
        study_id=study.id,
        study_instance_uid=study.study_instance_uid,
        accession_number=study.accession_number,
        patient_id=study.patient_id,
        expected_instance_count=study.instance_count,
        status=TransferStatus.PENDING,
        retry_count=0,
        maximum_retries=1,
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
    )
    session.add(job)
    session.flush()
    session.add(TransferDispatch(transfer_job_id=job.id, status="pending", attempt_count=0))
    append_audit_event(
        session,
        actor=AuditActor("user", request.actor_id),
        action="pacs.transfer.created",
        entity_type="transfer_job",
        entity_id=str(job.id),
        decision_reason="Authorized metadata-linked transfer request",
        correlation_id=request.correlation_id,
        request_id=request.idempotency_key,
        success=True,
        after_state={"study_id": str(study.id), "status": job.status.value},
    )
    return job


def _recover_transfer_finalization(
    session: Session,
    transfer_id: uuid.UUID,
    attempt_number: int,
    *,
    outcome: str,
    desired_status: TransferStatus,
    error_code: str | None,
    redacted_error: str | None,
    http_status: int | None,
    actor_id: str,
) -> TransferJob:
    """Persist explicit recovery evidence after post-call finalization fails."""

    session.rollback()
    job = session.scalar(select(TransferJob).where(TransferJob.id == transfer_id).with_for_update())
    attempt = session.scalar(
        select(TransferAttempt)
        .where(
            TransferAttempt.transfer_job_id == transfer_id,
            TransferAttempt.attempt_number == attempt_number,
        )
        .with_for_update()
    )
    if job is None or attempt is None:
        raise RuntimeError("transfer finalization could not be recovered") from None
    job.status = desired_status
    job.last_error_code = error_code
    attempt.outcome = outcome
    attempt.redacted_error = redacted_error
    attempt.completed_at = datetime.now(UTC)
    recovery_error_code = error_code or job.last_error_code or "FINALIZATION_UNAVAILABLE"
    recovery_error = redacted_error or "redacted transfer failure"
    try:
        if outcome == "failed":
            enqueue_incident_persistence(
                session,
                job,
                error_code=recovery_error_code,
                redacted_error=recovery_error,
                http_status=http_status,
                evidence={
                    "attempt_number": attempt_number,
                    "recovery": "transfer_finalization",
                },
            )
        append_audit_event(
            session,
            actor=AuditActor("system", actor_id),
            action="pacs.transfer.finalization_pending",
            entity_type="transfer_job",
            entity_id=str(job.id),
            decision_reason="External outcome persisted while finalization requires recovery",
            correlation_id=job.correlation_id,
            request_id=job.idempotency_key,
            success=False,
            policy_version="pacs-incident-v1",
            after_state={
                "attempt": attempt_number,
                "status": job.status.value,
                "outcome": outcome,
            },
            error_code=recovery_error_code,
        )
        session.commit()
    except Exception as audit_error:
        session.rollback()
        job = session.scalar(select(TransferJob).where(TransferJob.id == transfer_id))
        attempt = session.scalar(
            select(TransferAttempt).where(
                TransferAttempt.transfer_job_id == transfer_id,
                TransferAttempt.attempt_number == attempt_number,
            )
        )
        if job is None or attempt is None:
            raise RuntimeError("transfer finalization could not be recovered") from audit_error
        job.status = TransferStatus.FINALIZATION_PENDING
        job.last_error_code = "FINALIZATION_AUDIT_UNAVAILABLE"
        attempt.outcome = outcome
        attempt.redacted_error = redacted_error
        attempt.completed_at = datetime.now(UTC)
        if outcome == "failed":
            enqueue_incident_persistence(
                session,
                job,
                error_code=error_code or "FINALIZATION_AUDIT_UNAVAILABLE",
                redacted_error=redacted_error or "redacted transfer failure",
                http_status=http_status,
                evidence={
                    "attempt_number": attempt_number,
                    "recovery": "transfer_finalization_audit",
                },
            )
        session.commit()
    return job


def execute_transfer(
    session: Session, transfer_id: uuid.UUID, source_adapter: PacsAdapter, *, actor_id: str
) -> TransferJob:
    job = session.scalar(select(TransferJob).where(TransferJob.id == transfer_id).with_for_update())
    if job is None:
        raise TransferConflict("Transfer was not found")
    if job.status != TransferStatus.PENDING:
        return job
    study = session.get(PacsStudy, job.study_id)
    source = session.get(PacsNode, job.source_node_id)
    destination = session.get(PacsNode, job.destination_node_id)
    if study is None or source is None or destination is None:
        raise TransferConflict("Transfer references were not found")
    if study.node_id != source.id:
        raise TransferConflict("Transfer source and study are inconsistent")
    _validate_transfer_topology(source, destination)
    prior_attempts = session.scalar(
        select(func.count())
        .select_from(TransferAttempt)
        .where(TransferAttempt.transfer_job_id == job.id)
    )
    attempt_number = int(prior_attempts or 0) + 1
    if attempt_number > job.maximum_retries + 1:
        raise TransferConflict("Transfer attempt limit reached")

    job.status = TransferStatus.TRANSFERRING
    attempt = TransferAttempt(
        transfer_job_id=job.id,
        attempt_number=attempt_number,
        outcome="started",
        request_evidence={
            "orthanc_study_id": study.orthanc_study_id,
            "destination_adapter_key": destination.adapter_key,
        },
    )
    session.add(attempt)
    session.flush()
    append_audit_event(
        session,
        actor=AuditActor("user", actor_id),
        action="pacs.transfer.started",
        entity_type="transfer_job",
        entity_id=str(job.id),
        decision_reason="Persisted transfer intent before allowlisted external DICOM store",
        correlation_id=job.correlation_id,
        request_id=job.idempotency_key,
        success=True,
        after_state={"attempt": attempt_number, "status": job.status.value},
    )
    session.commit()

    success = False
    error_code: str | None = None
    redacted_error: str | None = None
    outcome = "accepted"
    desired_status = TransferStatus.TRANSFERRED
    try:
        response = source_adapter.send_study(study.orthanc_study_id, destination.adapter_key)
        if not response.accepted:
            raise DestinationUnavailable("PACS adapter did not accept the transfer")
        attempt.outcome = "accepted"
        attempt.response_evidence = {"response_path": response.response_path}
        job.status = TransferStatus.TRANSFERRED
        job.last_error_code = None
        success = True
    except Exception as exc:
        outcome = "failed"
        redacted_error = f"{type(exc).__name__}: transfer request failed"
        attempt.outcome = outcome
        attempt.redacted_error = redacted_error
        job.status = TransferStatus.FAILED
        error_code = (
            "DESTINATION_UNAVAILABLE"
            if isinstance(exc, DestinationUnavailable)
            else type(exc).__name__.upper()
        )
        job.last_error_code = error_code
        http_status = getattr(exc, "http_status", None)
        if type(http_status) is not int:
            http_status = None
        classification = classify_incident(
            IncidentClassificationInput(
                domain="pacs",
                source_entity_type="transfer_job",
                source_entity_id=str(job.id),
                error_code=error_code,
                error_message=redacted_error,
                http_status=http_status,
                transfer_status=job.status.value,
            )
        )
        try:
            record_transfer_failure_incident(
                session,
                job,
                classification,
                redacted_error=redacted_error,
                actor_id=actor_id,
            )
        except Exception as persistence_error:
            enqueue_incident_persistence(
                session,
                job,
                error_code=error_code,
                redacted_error=redacted_error,
                http_status=http_status,
                evidence={
                    "classification_rule": classification.rule_code,
                    "attempt_number": attempt_number,
                },
            )
            try:
                session.commit()
            except Exception as outbox_error:
                _recover_transfer_finalization(
                    session,
                    transfer_id,
                    attempt_number,
                    outcome=outcome,
                    desired_status=TransferStatus.FAILED,
                    error_code=error_code,
                    redacted_error=redacted_error,
                    http_status=http_status,
                    actor_id=actor_id,
                )
                raise RuntimeError("incident recovery could not be persisted") from outbox_error
            raise RuntimeError(
                "transfer failure incident queued for recovery"
            ) from persistence_error

    attempt.completed_at = datetime.now(UTC)
    job.retry_count = max(0, attempt_number - 1)
    try:
        append_audit_event(
            session,
            actor=AuditActor("user", actor_id),
            action="pacs.transfer.attempted",
            entity_type="transfer_job",
            entity_id=str(job.id),
            decision_reason="Allowlisted source-to-destination DICOM store",
            correlation_id=job.correlation_id,
            request_id=job.idempotency_key,
            success=success,
            after_state={"attempt": attempt_number, "status": job.status.value},
            error_code=job.last_error_code,
        )
        session.flush()
        session.commit()
    except Exception as finalization_error:
        _recover_transfer_finalization(
            session,
            transfer_id,
            attempt_number,
            outcome=outcome,
            desired_status=desired_status if success else TransferStatus.FAILED,
            error_code=error_code or job.last_error_code,
            redacted_error=redacted_error,
            http_status=http_status,
            actor_id=actor_id,
        )
        raise RuntimeError("transfer finalization requires recovery") from finalization_error
    return job


def reconcile_transfer(
    session: Session,
    transfer_id: uuid.UUID,
    source_adapter: PacsAdapter,
    destination_adapter: PacsAdapter,
    *,
    actor_id: str,
) -> ReconciliationResult:
    job = session.scalar(select(TransferJob).where(TransferJob.id == transfer_id).with_for_update())
    if job is None:
        raise TransferConflict("Transfer was not found")
    if job.status not in {
        TransferStatus.TRANSFERRED,
        TransferStatus.RECONCILIATION_FAILED,
    }:
        raise TransferConflict("Transfer is not ready for reconciliation")
    study = session.get(PacsStudy, job.study_id)
    source_node = session.get(PacsNode, job.source_node_id)
    destination_node = session.get(PacsNode, job.destination_node_id)
    if study is None or source_node is None or destination_node is None:
        raise TransferConflict("Transfer references were not found")
    if study.node_id != source_node.id:
        raise TransferConflict("Transfer source and study are inconsistent")
    _validate_transfer_topology(source_node, destination_node)
    source_matches = source_adapter.find_study(study.study_instance_uid)
    destination_matches = destination_adapter.find_study(study.study_instance_uid)
    source = source_matches[0] if len(source_matches) == 1 else None
    destination = destination_matches[0] if len(destination_matches) == 1 else None

    uid_match = bool(
        source
        and destination
        and source.study_instance_uid == job.study_instance_uid
        and destination.study_instance_uid == job.study_instance_uid
    )
    accession_match = bool(
        source
        and destination
        and source.accession_number == job.accession_number
        and destination.accession_number == job.accession_number
    )
    patient_match = bool(
        source
        and destination
        and source.patient_id == job.patient_id
        and destination.patient_id == job.patient_id
    )
    identifiers_match = uid_match and accession_match and patient_match
    counts_match = bool(
        source
        and destination
        and job.expected_instance_count > 0
        and source.instance_count == job.expected_instance_count
        and destination.instance_count == job.expected_instance_count
    )
    if source is None or destination is None:
        outcome = "missing_or_ambiguous"
    elif not identifiers_match:
        outcome = "identity_mismatch"
    elif not counts_match:
        outcome = "count_mismatch"
    else:
        outcome = "matched"
    result = ReconciliationResult(
        transfer_job_id=job.id,
        study_id=study.id,
        source_node_id=job.source_node_id,
        destination_node_id=job.destination_node_id,
        study_uid_match=uid_match,
        accession_match=accession_match,
        patient_id_match=patient_match,
        identifiers_match=identifiers_match,
        instance_counts_match=counts_match,
        source_instance_count=source.instance_count if source else 0,
        destination_instance_count=destination.instance_count if destination else 0,
        outcome=outcome,
        confidence=1.0,
        evidence_json={
            "source_matches": len(source_matches),
            "destination_matches": len(destination_matches),
        },
    )
    reconciliation_evidence = {
        "reconciliation_outcome": outcome,
        "reconciliation_identifiers_match": identifiers_match,
        "reconciliation_instance_counts_match": counts_match,
        "reconciliation_source_match_count": len(source_matches),
        "reconciliation_destination_match_count": len(destination_matches),
        "reconciliation_source_instance_count": source.instance_count if source else 0,
        "reconciliation_destination_instance_count": destination.instance_count
        if destination
        else 0,
    }
    session.add(result)
    if outcome == "matched":
        job.status = TransferStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
    else:
        job.status = TransferStatus.RECONCILIATION_FAILED
        job.last_error_code = outcome.upper()
        # Ambiguous or missing observations are not verified identity mismatches. Leave
        # classifier match inputs unset and let the explicit outcome classify as unknown.
        classification = classify_incident(
            IncidentClassificationInput(
                domain="pacs",
                source_entity_type="transfer_job",
                source_entity_id=str(job.id),
                error_code=outcome.upper(),
                error_message="Deterministic reconciliation mismatch",
                transfer_status=job.status.value,
                identifiers_match=identifiers_match if outcome != "missing_or_ambiguous" else None,
                instance_counts_match=counts_match if outcome != "missing_or_ambiguous" else None,
            )
        )
        record_transfer_failure_incident(
            session,
            job,
            classification,
            redacted_error="redacted transfer failure",
            actor_id=actor_id,
            evidence=reconciliation_evidence,
        )
    append_audit_event(
        session,
        actor=AuditActor("system", actor_id),
        action="pacs.transfer.reconciled",
        entity_type="transfer_job",
        entity_id=str(job.id),
        decision_reason="Deterministic source/destination metadata comparison",
        correlation_id=job.correlation_id,
        request_id=job.idempotency_key,
        success=outcome == "matched",
        policy_version="pacs-reconciliation-v1",
        after_state={
            "outcome": outcome,
            "identifiers_match": identifiers_match,
            "instance_counts_match": counts_match,
            "source_instance_count": source.instance_count if source else 0,
            "destination_instance_count": destination.instance_count if destination else 0,
        },
        error_code=None if outcome == "matched" else outcome.upper(),
    )
    session.flush()
    return result
