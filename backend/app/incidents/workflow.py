"""Human-controlled incident proposal and approval workflow.

This module persists intent and approval evidence only. It never calls a PACS adapter,
queues a retry, or changes DICOM data.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.auth.models import Role, User
from app.config import get_settings
from app.incidents.classifier import IncidentCategory
from app.incidents.models import (
    IncidentApprovalDecision,
    IncidentProposalStatus,
    IncidentRemediationApproval,
    IncidentRemediationProposal,
    PacsIncident,
    PacsIncidentApprovalState,
    PacsIncidentStatus,
)
from app.incidents.policy import (
    IncidentPolicyInput,
    IncidentPolicyResult,
    evaluate_incident_policy,
)
from app.pacs.models import PacsNode, TransferJob

PROPOSER_ROLES = frozenset({Role.PACS_ADMIN, Role.OPERATIONS_MANAGER})
APPROVER_ROLES = frozenset({Role.OPERATIONS_MANAGER, Role.SYSTEM_ADMIN})
REQUESTED_ACTION = "RETRY_TRANSFER"
MAX_HEALTH_AGE_SECONDS = 300


class IncidentWorkflowConflict(RuntimeError):
    """A proposal or decision cannot safely be applied to the current state."""

    def __init__(self, message: str, *, code: str = "INCIDENT_WORKFLOW_CONFLICT") -> None:
        super().__init__(message)
        self.code = code


def _health_age_seconds(node: PacsNode) -> int:
    if node.last_health_at is None:
        return MAX_HEALTH_AGE_SECONDS + 1
    checked_at = node.last_health_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - checked_at).total_seconds()))


def _policy_snapshot(
    incident: PacsIncident,
    job: TransferJob,
    destination: PacsNode,
) -> dict[str, Any]:
    settings = get_settings()
    configured_attempt_limit = min(job.maximum_retries, settings.max_auto_retries)
    return {
        "automation_enabled": settings.enable_auto_retry and configured_attempt_limit > 0,
        "configured_max_auto_retries": settings.max_auto_retries,
        "confidence_threshold": settings.low_confidence_threshold,
        "category": incident.category,
        "confidence": incident.confidence,
        "retry_candidate": incident.retry_candidate,
        "requested_action": REQUESTED_ACTION,
        "attempt_count": job.retry_count,
        "attempt_limit": max(1, configured_attempt_limit),
        "destination_node_id": str(destination.id),
        "health_node_id": str(destination.id),
        "destination_healthy": destination.last_health_status == "healthy",
        "destination_health_verified": destination.last_health_at is not None,
        "destination_health_age_seconds": _health_age_seconds(destination),
        "maximum_health_age_seconds": MAX_HEALTH_AGE_SECONDS,
        "execution_authorized": False,
        "approval_is_not_execution": True,
    }


def _approval_policy_input(
    proposal: IncidentRemediationProposal,
    incident: PacsIncident,
    job: TransferJob,
    destination: PacsNode,
    approver: User,
) -> IncidentPolicyInput:
    snapshot = _policy_snapshot(incident, job, destination)
    return IncidentPolicyInput(
        automation_enabled=bool(snapshot["automation_enabled"]),
        confidence=float(snapshot["confidence"]),
        confidence_threshold=float(snapshot["confidence_threshold"]),
        category=IncidentCategory(incident.category),
        retry_candidate=bool(snapshot["retry_candidate"]),
        requested_action=proposal.requested_action,
        attempt_count=int(snapshot["attempt_count"]),
        attempt_limit=int(snapshot["attempt_limit"]),
        destination_node_id=str(destination.id),
        health_node_id=str(destination.id),
        destination_healthy=bool(snapshot["destination_healthy"]),
        destination_health_verified=bool(snapshot["destination_health_verified"]),
        destination_health_age_seconds=int(snapshot["destination_health_age_seconds"]),
        maximum_health_age_seconds=MAX_HEALTH_AGE_SECONDS,
        proposer_id=proposal.proposer_id,
        approver_id=str(approver.id),
        approver_role=cast(
            Literal["operations_manager", "system_admin"], approver.role.value
        ),
        approver_authorized=approver.role in APPROVER_ROLES,
        approval_granted=True,
    )


def _load_incident_context(
    session: Session, incident_id: uuid.UUID, *, lock: bool
) -> tuple[PacsIncident, TransferJob, PacsNode]:
    query = select(PacsIncident).where(PacsIncident.id == incident_id)
    if lock:
        query = query.with_for_update()
    incident = session.scalar(query)
    if incident is None:
        raise IncidentWorkflowConflict("Incident was not found", code="INCIDENT_NOT_FOUND")
    job = session.get(TransferJob, incident.transfer_job_id)
    destination = session.get(PacsNode, incident.destination_node_id)
    if job is None or destination is None:
        raise IncidentWorkflowConflict(
            "Incident references incomplete transfer evidence", code="INCIDENT_EVIDENCE_INCOMPLETE"
        )
    return incident, job, destination


def create_remediation_proposal(
    session: Session,
    incident_id: uuid.UUID,
    *,
    proposer: User,
    requested_action: str,
    rationale: str,
    correlation_id: str,
    request_id: str,
) -> IncidentRemediationProposal:
    if proposer.role not in PROPOSER_ROLES:
        raise IncidentWorkflowConflict(
            "Role cannot propose remediation", code="PROPOSER_NOT_AUTHORIZED"
        )
    if requested_action != REQUESTED_ACTION:
        raise IncidentWorkflowConflict(
            "Only the allowlisted retry action can be proposed", code="ACTION_NOT_ALLOWLISTED"
        )
    incident, job, destination = _load_incident_context(session, incident_id, lock=True)
    if incident.status == PacsIncidentStatus.RESOLVED:
        raise IncidentWorkflowConflict(
            "Resolved incidents cannot receive proposals", code="INCIDENT_RESOLVED"
        )
    if incident.category != "connectivity" or not incident.retry_candidate:
        raise IncidentWorkflowConflict(
            "Only deterministic connectivity retry candidates can receive proposals",
            code="RETRY_NOT_ELIGIBLE",
        )
    if not rationale.strip():
        raise IncidentWorkflowConflict(
            "A proposal rationale is required", code="RATIONALE_REQUIRED"
        )
    existing = session.scalar(
        select(IncidentRemediationProposal)
        .where(
            IncidentRemediationProposal.incident_id == incident.id,
            IncidentRemediationProposal.status.in_(
                [IncidentProposalStatus.PENDING, IncidentProposalStatus.APPROVED]
            ),
        )
        .limit(1)
    )
    if existing is not None:
        raise IncidentWorkflowConflict(
            "Incident already has an active remediation proposal", code="ACTIVE_PROPOSAL_EXISTS"
        )
    proposal = IncidentRemediationProposal(
        incident_id=incident.id,
        requested_action=requested_action,
        proposer_id=str(proposer.id),
        proposer_role=proposer.role.value,
        rationale=rationale.strip(),
        policy_snapshot=_policy_snapshot(incident, job, destination),
        status=IncidentProposalStatus.PENDING,
    )
    session.add(proposal)
    incident.status = PacsIncidentStatus.PENDING_APPROVAL
    incident.approval_state = PacsIncidentApprovalState.PENDING
    session.flush()
    append_audit_event(
        session,
        actor=AuditActor("user", str(proposer.id)),
        action="pacs.incident.proposal.created",
        entity_type="incident_remediation_proposal",
        entity_id=str(proposal.id),
        decision_reason="Human operator proposed an allowlisted retry for incident review",
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        policy_version="pacs-incident-policy-v1",
        after_state={
            "incident_id": str(incident.id),
            "requested_action": proposal.requested_action,
            "status": proposal.status.value,
            "approval_is_not_execution": True,
        },
    )
    return proposal


def decide_remediation_proposal(
    session: Session,
    proposal_id: uuid.UUID,
    *,
    approver: User,
    decision: IncidentApprovalDecision,
    decision_reason: str,
    correlation_id: str,
    request_id: str,
) -> tuple[
    IncidentRemediationProposal,
    IncidentRemediationApproval,
    IncidentPolicyResult | None,
]:
    if approver.role not in APPROVER_ROLES:
        raise IncidentWorkflowConflict(
            "Role cannot approve or reject remediation", code="APPROVER_NOT_AUTHORIZED"
        )
    if not decision_reason.strip():
        raise IncidentWorkflowConflict(
            "A decision reason is required", code="DECISION_REASON_REQUIRED"
        )
    proposal = session.scalar(
        select(IncidentRemediationProposal)
        .where(IncidentRemediationProposal.id == proposal_id)
        .with_for_update()
    )
    if proposal is None:
        raise IncidentWorkflowConflict("Proposal was not found", code="PROPOSAL_NOT_FOUND")
    if proposal.status != IncidentProposalStatus.PENDING:
        raise IncidentWorkflowConflict(
            "Only pending proposals can receive one decision", code="PROPOSAL_ALREADY_DECIDED"
        )
    if proposal.proposer_id == str(approver.id):
        raise IncidentWorkflowConflict(
            "The proposer cannot approve or reject the same proposal",
            code="SEPARATION_OF_DUTIES_VIOLATION",
        )
    incident, job, destination = _load_incident_context(session, proposal.incident_id, lock=True)
    policy_result: IncidentPolicyResult | None = None
    if decision == IncidentApprovalDecision.APPROVED:
        policy_input = _approval_policy_input(proposal, incident, job, destination, approver)
        policy_result = evaluate_incident_policy(policy_input)
        if not policy_result.execution_authorized:
            raise IncidentWorkflowConflict(
                f"Approval denied by current policy: {policy_result.code.value}",
                code=policy_result.code.value,
            )
    proposal.status = (
        IncidentProposalStatus.APPROVED
        if decision == IncidentApprovalDecision.APPROVED
        else IncidentProposalStatus.REJECTED
    )
    proposal.decided_at = datetime.now(UTC)
    approval = IncidentRemediationApproval(
        proposal_id=proposal.id,
        approver_id=str(approver.id),
        approver_role=approver.role.value,
        decision=decision,
        decision_reason=decision_reason.strip(),
        policy_snapshot=_policy_snapshot(incident, job, destination),
    )
    session.add(approval)
    incident.approval_state = (
        PacsIncidentApprovalState.APPROVED
        if decision == IncidentApprovalDecision.APPROVED
        else PacsIncidentApprovalState.REJECTED
    )
    if decision == IncidentApprovalDecision.REJECTED:
        incident.status = PacsIncidentStatus.OPEN
    session.flush()
    append_audit_event(
        session,
        actor=AuditActor("user", str(approver.id)),
        action=(
            "pacs.incident.proposal.approved"
            if decision == IncidentApprovalDecision.APPROVED
            else "pacs.incident.proposal.rejected"
        ),
        entity_type="incident_remediation_approval",
        entity_id=str(approval.id),
        decision_reason=decision_reason.strip(),
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        policy_version="pacs-incident-policy-v1",
        after_state={
            "proposal_id": str(proposal.id),
            "incident_id": str(incident.id),
            "decision": approval.decision.value,
            "incident_approval_state": incident.approval_state.value,
            "execution_authorized": False,
            "approval_is_not_execution": True,
            "policy_code": policy_result.code.value if policy_result else "human_rejected",
        },
    )
    return proposal, approval, policy_result
