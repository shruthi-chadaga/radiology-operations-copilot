"""Celery PACS transfer tasks. Retries are disabled until deterministic Phase 4 policy."""

import uuid

from app.db.session import SessionLocal
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.dispatch import publish_pending_transfer_dispatches
from app.pacs.models import TransferJob
from app.pacs.transfer import execute_transfer
from app.workers.celery_app import celery_app


@celery_app.task(  # type: ignore[untyped-decorator]
    name="pacs.execute_transfer", autoretry_for=(), max_retries=0
)
def execute_transfer_task(transfer_id: str) -> dict[str, str]:
    adapters = get_pacs_adapters()
    with SessionLocal() as session:
        job = session.get(TransferJob, uuid.UUID(transfer_id))
        if job is None:
            return {"status": "not_found", "transfer_id": transfer_id}
        source = adapters.get("source")
        if source is None:
            return {"status": "adapter_missing", "transfer_id": transfer_id}
        execute_transfer(session, job.id, source, actor_id="celery-worker")
        session.commit()
        return {"status": job.status.value, "transfer_id": transfer_id}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="pacs.publish_transfer_outbox", autoretry_for=(), max_retries=0
)
def publish_transfer_outbox_task() -> dict[str, int]:
    with SessionLocal() as session:
        published = publish_pending_transfer_dispatches(
            session, lambda transfer_id: execute_transfer_task.delay(transfer_id)
        )
        session.commit()
        return {"published": published}
