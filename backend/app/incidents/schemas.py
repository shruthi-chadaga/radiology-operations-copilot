"""Strict incident review and human-approval API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IncidentProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    requested_action: Literal["RETRY_TRANSFER"]
    rationale: str = Field(min_length=1, max_length=1000)


class IncidentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decision_reason: str = Field(min_length=1, max_length=1000)


class IncidentApprovalResponse(BaseModel):
    id: str
    proposal_id: str
    approver_id: str
    approver_role: str
    decision: str
    decision_reason: str
    policy_snapshot: dict[str, Any]
    created_at: datetime


class IncidentProposalResponse(BaseModel):
    id: str
    incident_id: str
    requested_action: str
    proposer_id: str
    proposer_role: str
    rationale: str
    policy_snapshot: dict[str, Any]
    status: str
    created_at: datetime
    decided_at: datetime | None
    approval: IncidentApprovalResponse | None


class IncidentResponse(BaseModel):
    id: str
    incident_number: str
    transfer_job_id: str
    study_id: str
    source_node_id: str
    destination_node_id: str
    category: str
    severity: str
    status: str
    approval_state: str
    retry_candidate: bool
    requires_human_review: bool
    confidence: float
    rule_code: str
    redacted_summary: str
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    proposals: list[IncidentProposalResponse]


class IncidentPage(BaseModel):
    items: list[IncidentResponse]


class OutboxResponse(BaseModel):
    id: str
    transfer_job_id: str
    error_code: str
    status: str
    attempt_count: int
    last_attempt_at: datetime | None
    completed_at: datetime | None
    last_error: str | None


class OutboxPage(BaseModel):
    items: list[OutboxResponse]


class OutboxDrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    limit: int = Field(default=20, ge=1, le=100)


class OutboxDrainResponse(BaseModel):
    selected: int
    completed: int
    deferred: int
    failed: int
