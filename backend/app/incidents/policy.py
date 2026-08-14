"""Fail-closed deterministic policy evaluation for incident remediation.

This module evaluates evidence and approval context only. It never calls adapters, queues
work, mutates persistence, or authorizes prohibited actions.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator

from app.incidents.classifier import IncidentCategory


class PolicyDecision(StrEnum):
    AUTHORIZED = "authorized"
    DENIED = "denied"


class PolicyDecisionCode(StrEnum):
    EXECUTION_AUTHORIZED = "execution_authorized"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    LOW_CONFIDENCE = "low_confidence"
    CATEGORY_PROHIBITED = "category_prohibited"
    NOT_RETRY_CANDIDATE = "not_retry_candidate"
    ACTION_NOT_ALLOWLISTED = "action_not_allowlisted"
    ATTEMPT_LIMIT_REACHED = "attempt_limit_reached"
    DESTINATION_HEALTH_UNVERIFIED = "destination_health_unverified"
    DESTINATION_HEALTH_STALE = "destination_health_stale"
    DESTINATION_UNHEALTHY = "destination_unhealthy"
    SEPARATION_OF_DUTIES_VIOLATION = "separation_of_duties_violation"
    APPROVER_NOT_AUTHORIZED = "approver_not_authorized"
    APPROVAL_REQUIRED = "approval_required"


class IncidentPolicyInput(BaseModel):
    """Strict evidence and approval context for one proposed remediation.

    The caller must provide a policy snapshot from authoritative persisted/configured state.
    A name alone is never treated as proof of approval or authorization.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    automation_enabled: StrictBool
    confidence: float = Field(ge=0, le=1)
    confidence_threshold: float = Field(ge=0, le=1)
    category: IncidentCategory
    retry_candidate: StrictBool
    requested_action: StrictStr = Field(min_length=1, max_length=64)
    attempt_count: int = Field(ge=0, le=100)
    attempt_limit: int = Field(ge=1, le=1)
    destination_node_id: StrictStr = Field(min_length=1, max_length=80)
    health_node_id: StrictStr = Field(min_length=1, max_length=80)
    destination_healthy: StrictBool
    destination_health_verified: StrictBool
    destination_health_age_seconds: int = Field(ge=0, le=3600)
    maximum_health_age_seconds: int = Field(ge=1, le=3600)
    proposer_id: StrictStr = Field(min_length=1, max_length=80)
    approver_id: StrictStr | None = Field(default=None, max_length=80)
    approver_role: Literal["operations_manager", "system_admin"] | None = None
    approver_authorized: StrictBool
    approval_granted: StrictBool

    @field_validator(
        "requested_action",
        "proposer_id",
        "approver_id",
        "destination_node_id",
        "health_node_id",
    )
    @classmethod
    def reject_blank_identity_or_action(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("value must not be blank")
        return value


class IncidentPolicyResult(BaseModel):
    """Policy decision; execution permission is only true for the final gated result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decision: PolicyDecision
    code: PolicyDecisionCode
    execution_authorized: Literal[True, False]
    requires_human_approval: bool


_ALLOWED_CATEGORY = IncidentCategory.CONNECTIVITY
_ALLOWED_ACTION = "RETRY_TRANSFER"


def evaluate_incident_policy(payload: IncidentPolicyInput) -> IncidentPolicyResult:
    """Apply policy gates in deterministic safety precedence order."""

    checks = (
        (
            not payload.automation_enabled,
            PolicyDecisionCode.KILL_SWITCH_ACTIVE,
            False,
        ),
        (
            payload.confidence < payload.confidence_threshold,
            PolicyDecisionCode.LOW_CONFIDENCE,
            True,
        ),
        (
            payload.category != _ALLOWED_CATEGORY,
            PolicyDecisionCode.CATEGORY_PROHIBITED,
            True,
        ),
        (
            not payload.retry_candidate,
            PolicyDecisionCode.NOT_RETRY_CANDIDATE,
            True,
        ),
        (
            payload.requested_action != _ALLOWED_ACTION,
            PolicyDecisionCode.ACTION_NOT_ALLOWLISTED,
            True,
        ),
        (
            payload.attempt_count >= payload.attempt_limit,
            PolicyDecisionCode.ATTEMPT_LIMIT_REACHED,
            True,
        ),
        (
            payload.destination_node_id != payload.health_node_id
            or not payload.destination_health_verified,
            PolicyDecisionCode.DESTINATION_HEALTH_UNVERIFIED,
            True,
        ),
        (
            payload.destination_health_age_seconds > payload.maximum_health_age_seconds,
            PolicyDecisionCode.DESTINATION_HEALTH_STALE,
            True,
        ),
        (
            not payload.destination_healthy,
            PolicyDecisionCode.DESTINATION_UNHEALTHY,
            True,
        ),
        (
            payload.approver_id is None or payload.approver_role is None,
            PolicyDecisionCode.APPROVAL_REQUIRED,
            True,
        ),
        (
            not payload.approver_authorized,
            PolicyDecisionCode.APPROVER_NOT_AUTHORIZED,
            True,
        ),
        (
            payload.approval_granted is False,
            PolicyDecisionCode.APPROVAL_REQUIRED,
            True,
        ),
        (
            payload.approver_id == payload.proposer_id,
            PolicyDecisionCode.SEPARATION_OF_DUTIES_VIOLATION,
            True,
        ),
    )
    for failed, code, requires_approval in checks:
        if failed:
            return IncidentPolicyResult(
                decision=PolicyDecision.DENIED,
                code=code,
                execution_authorized=False,
                requires_human_approval=requires_approval,
            )

    return IncidentPolicyResult(
        decision=PolicyDecision.AUTHORIZED,
        code=PolicyDecisionCode.EXECUTION_AUTHORIZED,
        execution_authorized=True,
        requires_human_approval=False,
    )
