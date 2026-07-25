"""Durable at-least-once publication of duplicate-safe transfer tasks."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.pacs.models import TransferDispatch, TransferJob


def publish_pending_transfer_dispatches(
    session: Session,
    send: Callable[[str], object],
    *,
    transfer_id: uuid.UUID | None = None,
    limit: int = 50,
) -> int:
    statement = (
        select(TransferDispatch)
        .where(TransferDispatch.status == "pending")
        .order_by(TransferDispatch.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if transfer_id is not None:
        statement = statement.where(TransferDispatch.transfer_job_id == transfer_id)
    published = 0
    for dispatch in session.scalars(statement):
        job = session.get(TransferJob, dispatch.transfer_job_id)
        if job is None:
            dispatch.status = "orphaned"
            dispatch.last_error = "Transfer job was not found"
            continue
        dispatch.attempt_count += 1
        try:
            send(str(job.id))
        except Exception as exc:
            dispatch.last_error = f"{type(exc).__name__}: broker publication failed"[:200]
            append_audit_event(
                session,
                actor=AuditActor("system", "transfer-outbox"),
                action="pacs.transfer.dispatch_failed",
                entity_type="transfer_job",
                entity_id=str(job.id),
                decision_reason="Broker publication failed; durable outbox remains pending",
                correlation_id=job.correlation_id,
                request_id=job.idempotency_key,
                success=False,
                error_code="BROKER_PUBLICATION_FAILED",
            )
            continue
        dispatch.status = "published"
        dispatch.published_at = datetime.now(UTC)
        dispatch.last_error = None
        published += 1
        append_audit_event(
            session,
            actor=AuditActor("system", "transfer-outbox"),
            action="pacs.transfer.dispatched",
            entity_type="transfer_job",
            entity_id=str(job.id),
            decision_reason="Durable transfer outbox published to the worker broker",
            correlation_id=job.correlation_id,
            request_id=job.idempotency_key,
            success=True,
            after_state={"dispatch_attempt": dispatch.attempt_count},
        )
    session.flush()
    return published
