"""Celery application for bounded local background jobs."""

from celery import Celery  # type: ignore[import-untyped]

from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "radiology_ops",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.pacs_tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={
        "publish-pending-transfer-outbox": {
            "task": "pacs.publish_transfer_outbox",
            "schedule": 5.0,
        }
    },
)


@celery_app.task(name="foundation.ping")  # type: ignore[untyped-decorator]
def ping() -> dict[str, str | bool]:
    return {"status": "ok", "synthetic_only": True}
