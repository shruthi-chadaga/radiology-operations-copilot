"""Persisted Imaging Workspace worklist and authored report models."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImagingWorklistStatus(StrEnum):
    SCHEDULED = "scheduled"
    RECEIVED = "received"
    READY_FOR_REVIEW = "ready_for_review"
    IN_REVIEW = "in_review"
    REPORT_DRAFT = "report_draft"
    CORRECTION_PENDING = "correction_pending"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"


class ImagingPriority(StrEnum):
    ROUTINE = "routine"
    URGENT = "urgent"
    STAT = "stat"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    CORRECTION_PENDING = "correction_pending"


class ReportVersionKind(StrEnum):
    DRAFT = "draft"
    FINAL = "final"
    CORRECTION = "correction"


class ImagingWorklistItem(Base):
    """Durable projection joining scheduling and observed PACS metadata."""

    __tablename__ = "imaging_worklist_items"
    __table_args__ = (
        UniqueConstraint("pacs_study_id", name="uq_imaging_worklist_pacs_study"),
        UniqueConstraint("appointment_id", name="uq_imaging_worklist_appointment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("synthetic_patients.id"), nullable=True, index=True
    )
    pacs_patient_id: Mapped[str] = mapped_column(String(64), index=True)
    pacs_study_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pacs_studies.id"), nullable=True, index=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointments.id"), nullable=True, index=True
    )
    accession_number: Mapped[str] = mapped_column(String(64), index=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    study_description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    workflow_status: Mapped[ImagingWorklistStatus] = mapped_column(
        Enum(ImagingWorklistStatus, native_enum=False, length=32),
        default=ImagingWorklistStatus.SCHEDULED,
        index=True,
    )
    priority: Mapped[ImagingPriority] = mapped_column(
        Enum(ImagingPriority, native_enum=False, length=16),
        default=ImagingPriority.ROUTINE,
        index=True,
    )
    assigned_reader_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    report_status: Mapped[str] = mapped_column(String(24), default="not_started")
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )


class RadiologyReport(Base):
    """Report workflow state; authored text lives in immutable versions."""

    __tablename__ = "radiology_reports"
    __table_args__ = (UniqueConstraint("study_id", name="uq_radiology_report_study"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pacs_studies.id"), index=True
    )
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, native_enum=False, length=24),
        default=ReportStatus.DRAFT,
        index=True,
    )
    current_version_number: Mapped[int | None] = mapped_column(nullable=True)
    finalized_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now
    )


class RadiologyReportVersion(Base):
    """Append-only authored report content; corrections create new versions."""

    __tablename__ = "radiology_report_versions"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "version_number",
            name="uq_radiology_report_version_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("radiology_reports.id"), index=True
    )
    version_number: Mapped[int] = mapped_column()
    kind: Mapped[ReportVersionKind] = mapped_column(
        Enum(ReportVersionKind, native_enum=False, length=16)
    )
    author_id: Mapped[str] = mapped_column(String(64))
    indication: Mapped[str] = mapped_column(String(400), default="")
    findings: Mapped[str] = mapped_column(String(12000), default="")
    impression: Mapped[str] = mapped_column(String(4000), default="")
    correction_reason: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
