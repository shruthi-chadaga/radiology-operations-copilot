"""Idempotent PACS transfer execution and metadata-only reconciliation."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
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
    try:
        response = source_adapter.send_study(study.orthanc_study_id, destination.adapter_key)
        if not response.accepted:
            raise TransferConflict("PACS adapter did not accept the transfer")
        attempt.outcome = "accepted"
        attempt.response_evidence = {"response_path": response.response_path}
        job.status = TransferStatus.TRANSFERRED
        job.last_error_code = None
        success = True
    except Exception as exc:
        attempt.outcome = "failed"
        attempt.redacted_error = f"{type(exc).__name__}: transfer request failed"
        job.status = TransferStatus.FAILED
        job.last_error_code = type(exc).__name__.upper()
        success = False
    attempt.completed_at = datetime.now(UTC)
    job.retry_count = max(0, attempt_number - 1)
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
    if job.status not in {TransferStatus.TRANSFERRED, TransferStatus.RECONCILIATION_FAILED}:
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
    session.add(result)
    if outcome == "matched":
        job.status = TransferStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
    else:
        job.status = TransferStatus.RECONCILIATION_FAILED
        job.last_error_code = outcome.upper()
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
        after_state={"outcome": outcome, "identifiers_match": identifiers_match},
        error_code=None if outcome == "matched" else outcome.upper(),
    )
    session.flush()
    return result
