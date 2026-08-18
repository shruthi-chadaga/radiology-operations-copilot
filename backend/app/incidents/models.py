"""Persisted PACS incident evidence and human-remediation state."""

import uuid
from datetime import UTC, datetime
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


class PacsIncidentStatus(StrEnum):
    OPEN = "open"
    PENDING_APPROVAL = "pending_approval"
    RESOLVED = "resolved"


class PacsIncidentApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class IncidentProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class IncidentApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class PacsIncident(Base):
    __tablename__ = "pacs_incidents"
    __table_args__ = (
        UniqueConstraint("transfer_job_id", name="uq_pacs_incident_transfer_job"),
        CheckConstraint(
            "category IN ('no_incident', 'connectivity', 'identity_mismatch', "
            "'count_mismatch', 'unauthorized', 'configuration', 'destructive_action', "
            "'non_allowlisted_action', 'unknown')",
            name="ck_pacs_incident_category",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_pacs_incident_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'pending_approval', 'resolved')",
            name="ck_pacs_incident_status",
        ),
        CheckConstraint(
            "approval_state IN ('pending', 'approved', 'rejected')",
            name="ck_pacs_incident_approval_state",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_pacs_incident_confidence"),
        CheckConstraint("last_failure_count >= 1", name="ck_pacs_incident_failure_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    transfer_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transfer_jobs.id"), index=True)
    study_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_studies.id"), index=True)
    source_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"))
    destination_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_nodes.id"))
    category: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[PacsIncidentStatus] = mapped_column(
        Enum(
            PacsIncidentStatus,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=PacsIncidentStatus.OPEN,
        index=True,
    )
    approval_state: Mapped[PacsIncidentApprovalState] = mapped_column(
        Enum(
            PacsIncidentApprovalState,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=PacsIncidentApprovalState.PENDING,
        index=True,
    )
    retry_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    rule_code: Mapped[str] = mapped_column(String(80))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    redacted_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_failure_count: Mapped[int] = mapped_column(Integer, default=1)


class IncidentRemediationProposal(Base):
    """Immutable proposal intent; approval never executes a PACS action."""

    __tablename__ = "incident_remediation_proposals"
    __table_args__ = (
        CheckConstraint(
            "requested_action = 'RETRY_TRANSFER'",
            name="ck_incident_proposal_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_incident_proposal_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pacs_incidents.id"), index=True)
    requested_action: Mapped[str] = mapped_column(String(64))
    proposer_id: Mapped[str] = mapped_column(String(64), index=True)
    proposer_role: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[IncidentProposalStatus] = mapped_column(
        Enum(
            IncidentProposalStatus,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=IncidentProposalStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentRemediationApproval(Base):
    """Append-only decision record for one remediation proposal."""

    __tablename__ = "incident_remediation_approvals"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_incident_approval_proposal"),
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_incident_approval_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incident_remediation_proposals.id"), index=True
    )
    approver_id: Mapped[str] = mapped_column(String(64), index=True)
    approver_role: Mapped[str] = mapped_column(String(32))
    decision: Mapped[IncidentApprovalDecision] = mapped_column(
        Enum(
            IncidentApprovalDecision,
            native_enum=False,
            length=32,
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    decision_reason: Mapped[str] = mapped_column(Text)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
