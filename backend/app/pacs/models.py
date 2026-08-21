"""Metadata-only PACS inventory and idempotent transfer persistence."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransferStatus(StrEnum):
    PENDING = "pending"
    TRANSFERRING = "transferring"
    TRANSFERRED = "transferred"
    COMPLETED = "completed"
    FAILED = "failed"
    FINALIZATION_PENDING = "finalization_pending"
    RECONCILIATION_FAILED = "reconciliation_failed"


class PacsNode(Base):
    __tablename__ = "pacs_nodes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    node_type: Mapped[str] = mapped_column(String(24), index=True)
    base_url: Mapped[str] = mapped_column(String(300))
    dicom_ae_title: Mapped[str] = mapped_column(String(32))
    dicom_host: Mapped[str] = mapped_column(String(160))
    dicom_port: Mapped[int] = mapped_column(Integer)
    adapter_key: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_health_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PacsHealthCheck(Base):
    __tablename__ = "pacs_health_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    latency_ms: Mapped[int] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    redacted_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class PacsStudy(Base):
    __tablename__ = "pacs_studies"
    __table_args__ = (
        UniqueConstraint("node_id", "orthanc_study_id", name="uq_pacs_study_node_orthanc"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"), index=True)
    orthanc_study_id: Mapped[str] = mapped_column(String(80))
    study_instance_uid: Mapped[str] = mapped_column(String(128), index=True)
    accession_number: Mapped[str] = mapped_column(String(64), index=True)
    patient_id: Mapped[str] = mapped_column(String(64), index=True)
    study_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    study_description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    patient_birth_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    patient_sex: Mapped[str | None] = mapped_column(String(4), nullable=True)
    series_count: Mapped[int] = mapped_column(Integer)
    instance_count: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class TransferJob(Base):
    __tablename__ = "transfer_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"))
    destination_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"))
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_studies.id"), index=True)
    study_instance_uid: Mapped[str] = mapped_column(String(128))
    accession_number: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[str] = mapped_column(String(64))
    expected_instance_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, native_enum=False, length=32),
        default=TransferStatus.PENDING,
        index=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    maximum_retries: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    correlation_id: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class TransferDispatch(Base):
    __tablename__ = "transfer_dispatches"

    transfer_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transfer_jobs.id"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TransferAttempt(Base):
    __tablename__ = "transfer_attempts"
    __table_args__ = (
        UniqueConstraint("transfer_job_id", "attempt_number", name="uq_transfer_attempt_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transfer_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfer_jobs.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32))
    request_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    redacted_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transfer_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfer_jobs.id"), index=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_studies.id"))
    source_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"))
    destination_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"))
    study_uid_match: Mapped[bool] = mapped_column(Boolean)
    accession_match: Mapped[bool] = mapped_column(Boolean)
    patient_id_match: Mapped[bool] = mapped_column(Boolean)
    identifiers_match: Mapped[bool] = mapped_column(Boolean)
    instance_counts_match: Mapped[bool] = mapped_column(Boolean)
    source_instance_count: Mapped[int] = mapped_column(Integer)
    destination_instance_count: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class ProcedureStepStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"


class ProcedureStep(Base):
    """MPPS-lite record of one modality procedure step lifecycle.

    Append-only lifecycle evidence: a step starts once and ends exactly once,
    either completed (with performed series count) or discontinued (with a
    human-readable reason). It never modifies DICOM data or PACS state.
    """

    __tablename__ = "procedure_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed', 'discontinued')",
            name="ck_procedure_step_status",
        ),
        UniqueConstraint("accession_number", "step_number", name="uq_procedure_step_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    accession_number: Mapped[str] = mapped_column(String(64), index=True)
    step_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[ProcedureStepStatus] = mapped_column(
        String(24),
        default=ProcedureStepStatus.IN_PROGRESS,
        server_default="in_progress",
        index=True,
    )
    started_by: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    performed_series_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
