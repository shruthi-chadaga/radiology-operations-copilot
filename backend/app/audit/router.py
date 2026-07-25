"""Read-only audit routes. There are intentionally no mutation routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.audit.schemas import AuditEventResponse, AuditPage
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"])
_AUDIT_ROLES = {Role.AUDITOR, Role.OPERATIONS_MANAGER, Role.SYSTEM_ADMIN}


@router.get("", response_model=AuditPage)
def list_audit_events(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditPage:
    if user.role not in _AUDIT_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit))
    return AuditPage(
        items=[
            AuditEventResponse(
                id=str(event.id),
                timestamp=event.timestamp,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                action=event.action,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                before_state=event.before_state,
                after_state=event.after_state,
                decision_reason=event.decision_reason,
                policy_version=event.policy_version,
                model_name=event.model_name,
                prompt_version=event.prompt_version,
                correlation_id=event.correlation_id,
                request_id=event.request_id,
                success=event.success,
                error_code=event.error_code,
                error_message=event.error_message,
            )
            for event in events
        ]
    )
