"""Durable evidence that a transfer failure still needs incident persistence."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IncidentPersistenceOutbox(Base):
    __tablename__ = "incident_persistence_outbox"
    __table_args__ = (
        UniqueConstraint("transfer_job_id", name="uq_incident_outbox_transfer_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transfer_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transfer_jobs.id"), index=True
    )
    error_code: Mapped[str] = mapped_column(String(80))
    redacted_error: Mapped[str] = mapped_column(String(200))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
