"""Protected human review APIs for deterministic PACS incidents."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.session import get_db
from app.incidents.models import (
    IncidentApprovalDecision,
    IncidentRemediationApproval,
    IncidentRemediationProposal,
    PacsIncident,
)
from app.incidents.outbox import IncidentPersistenceOutbox
from app.incidents.recovery import drain_incident_persistence_outbox
from app.incidents.schemas import (
    IncidentApprovalResponse,
    IncidentDecisionRequest,
    IncidentPage,
    IncidentProposalCreateRequest,
    IncidentProposalResponse,
    IncidentResponse,
    OutboxDrainRequest,
    OutboxDrainResponse,
    OutboxPage,
    OutboxResponse,
)
from app.incidents.workflow import (
    APPROVER_ROLES,
    PROPOSER_ROLES,
    IncidentWorkflowConflict,
    create_remediation_proposal,
    decide_remediation_proposal,
)

router = APIRouter(prefix="/incidents", tags=["incident-review"])
_READ_ROLES = PROPOSER_ROLES | APPROVER_ROLES | {Role.AUDITOR}


def _authorize(user: User, roles: frozenset[Role]) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _request_ids(request: Request) -> tuple[str, str]:
    request_id = request.headers.get("x-request-id", f"local-{uuid.uuid4().hex[:12]}")[:160]
    correlation_id = request.headers.get("x-correlation-id", request_id)[:160]
    return request_id, correlation_id


def _audit_denial(
    db: Session,
    request: Request,
    *,
    user: User,
    entity_type: str,
    entity_id: str,
    error_code: str,
    reason: str,
) -> None:
    request_id, correlation_id = _request_ids(request)
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="pacs.incident.workflow.denied",
        entity_type=entity_type,
        entity_id=entity_id,
        decision_reason=reason,
        correlation_id=correlation_id,
        request_id=request_id,
        success=False,
        policy_version="pacs-incident-policy-v1",
        error_code=error_code,
    )
    db.commit()


def _approval_response(
    approval: IncidentRemediationApproval | None,
) -> IncidentApprovalResponse | None:
    if approval is None:
        return None
    return IncidentApprovalResponse(
        id=str(approval.id),
        proposal_id=str(approval.proposal_id),
        approver_id=approval.approver_id,
        approver_role=approval.approver_role,
        decision=approval.decision.value,
        decision_reason=approval.decision_reason,
        policy_snapshot=approval.policy_snapshot,
        created_at=approval.created_at,
    )


def _proposal_response(
    db: Session,
    proposal: IncidentRemediationProposal,
) -> IncidentProposalResponse:
    approval = db.scalar(
        select(IncidentRemediationApproval).where(
            IncidentRemediationApproval.proposal_id == proposal.id
        )
    )
    return IncidentProposalResponse(
        id=str(proposal.id),
        incident_id=str(proposal.incident_id),
        requested_action=proposal.requested_action,
        proposer_id=proposal.proposer_id,
        proposer_role=proposal.proposer_role,
        rationale=proposal.rationale,
        policy_snapshot=proposal.policy_snapshot,
        status=proposal.status.value,
        created_at=proposal.created_at,
        decided_at=proposal.decided_at,
        approval=_approval_response(approval),
    )


def _incident_response(db: Session, incident: PacsIncident) -> IncidentResponse:
    proposals = db.scalars(
        select(IncidentRemediationProposal)
        .where(IncidentRemediationProposal.incident_id == incident.id)
        .order_by(IncidentRemediationProposal.created_at.desc())
    )
    return IncidentResponse(
        id=str(incident.id),
        incident_number=incident.incident_number,
        transfer_job_id=str(incident.transfer_job_id),
        study_id=str(incident.study_id),
        source_node_id=str(incident.source_node_id),
        destination_node_id=str(incident.destination_node_id),
        category=incident.category,
        severity=incident.severity,
        status=incident.status.value,
        approval_state=incident.approval_state.value,
        retry_candidate=incident.retry_candidate,
        requires_human_review=incident.requires_human_review,
        confidence=incident.confidence,
        rule_code=incident.rule_code,
        redacted_summary=incident.redacted_summary,
        evidence=incident.evidence_json,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        proposals=[_proposal_response(db, item) for item in proposals],
    )


def _outbox_response(item: IncidentPersistenceOutbox) -> OutboxResponse:
    return OutboxResponse(
        id=str(item.id),
        transfer_job_id=str(item.transfer_job_id),
        error_code=item.error_code,
        status=item.status,
        attempt_count=item.attempt_count,
        last_attempt_at=item.last_attempt_at,
        completed_at=item.completed_at,
        last_error=item.last_error,
    )


@router.get("", response_model=IncidentPage)
def list_incidents(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> IncidentPage:
    _authorize(user, _READ_ROLES)
    incidents = db.scalars(
        select(PacsIncident).order_by(PacsIncident.updated_at.desc()).limit(200)
    )
    return IncidentPage(items=[_incident_response(db, item) for item in incidents])


@router.get("/outbox", response_model=OutboxPage)
def list_outbox(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OutboxPage:
    _authorize(user, _READ_ROLES)
    items = db.scalars(
        select(IncidentPersistenceOutbox)
        .order_by(IncidentPersistenceOutbox.created_at)
        .limit(200)
    )
    return OutboxPage(items=[_outbox_response(item) for item in items])


@router.post("/outbox/drain", response_model=OutboxDrainResponse)
def drain_outbox(
    payload: OutboxDrainRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OutboxDrainResponse:
    _authorize(user, APPROVER_ROLES)
    request_id, correlation_id = _request_ids(request)
    result = drain_incident_persistence_outbox(
        db,
        actor_id=str(user.id),
        limit=payload.limit,
    )
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="pacs.incident.outbox.drained",
        entity_type="incident_persistence_outbox",
        entity_id="batch",
        decision_reason=(
            "Operator requested bounded incident evidence recovery; "
            "no remediation was executed"
        ),
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        policy_version="pacs-incident-v1",
        after_state={
            "selected": result.selected,
            "completed": result.completed,
            "deferred": result.deferred,
            "failed": result.failed,
        },
    )
    db.commit()
    return OutboxDrainResponse(
        selected=result.selected,
        completed=result.completed,
        deferred=result.deferred,
        failed=result.failed,
    )


@router.post("/proposals/{proposal_id}/approve", response_model=IncidentProposalResponse)
def approve_proposal(
    proposal_id: uuid.UUID,
    payload: IncidentDecisionRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> IncidentProposalResponse:
    _authorize(user, APPROVER_ROLES)
    request_id, correlation_id = _request_ids(request)
    try:
        proposal, _, _ = decide_remediation_proposal(
            db,
            proposal_id,
            approver=user,
            decision=IncidentApprovalDecision.APPROVED,
            decision_reason=payload.decision_reason,
            correlation_id=correlation_id,
            request_id=request_id,
        )
        db.commit()
    except IncidentWorkflowConflict as exc:
        db.rollback()
        _audit_denial(
            db,
            request,
            user=user,
            entity_type="incident_remediation_proposal",
            entity_id=str(proposal_id),
            error_code=exc.code,
            reason=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code) from exc
    return _proposal_response(db, proposal)


@router.post("/proposals/{proposal_id}/reject", response_model=IncidentProposalResponse)
def reject_proposal(
    proposal_id: uuid.UUID,
    payload: IncidentDecisionRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> IncidentProposalResponse:
    _authorize(user, APPROVER_ROLES)
    request_id, correlation_id = _request_ids(request)
    try:
        proposal, _, _ = decide_remediation_proposal(
            db,
            proposal_id,
            approver=user,
            decision=IncidentApprovalDecision.REJECTED,
            decision_reason=payload.decision_reason,
            correlation_id=correlation_id,
            request_id=request_id,
        )
        db.commit()
    except IncidentWorkflowConflict as exc:
        db.rollback()
        _audit_denial(
            db,
            request,
            user=user,
            entity_type="incident_remediation_proposal",
            entity_id=str(proposal_id),
            error_code=exc.code,
            reason=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code) from exc
    return _proposal_response(db, proposal)


@router.post("/{incident_id}/proposals", response_model=IncidentProposalResponse, status_code=201)
def propose_remediation(
    incident_id: uuid.UUID,
    payload: IncidentProposalCreateRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> IncidentProposalResponse:
    _authorize(user, PROPOSER_ROLES)
    request_id, correlation_id = _request_ids(request)
    try:
        proposal = create_remediation_proposal(
            db,
            incident_id,
            proposer=user,
            requested_action=payload.requested_action,
            rationale=payload.rationale,
            correlation_id=correlation_id,
            request_id=request_id,
        )
        db.commit()
    except IncidentWorkflowConflict as exc:
        db.rollback()
        _audit_denial(
            db,
            request,
            user=user,
            entity_type="pacs_incident",
            entity_id=str(incident_id),
            error_code=exc.code,
            reason=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code) from exc
    return _proposal_response(db, proposal)


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> IncidentResponse:
    _authorize(user, _READ_ROLES)
    incident = db.get(PacsIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _incident_response(db, incident)
