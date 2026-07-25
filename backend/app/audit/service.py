"""The only application service that creates audit records.

Deliberately exposes no update or delete operation.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.audit.models import AuditEvent


@dataclass(frozen=True)
class AuditActor:
    actor_type: str
    actor_id: str | None


def append_audit_event(
    session: Session,
    *,
    actor: AuditActor,
    action: str,
    entity_type: str,
    entity_id: str,
    decision_reason: str,
    correlation_id: str,
    request_id: str,
    success: bool,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    policy_version: str | None = None,
    model_name: str | None = None,
    prompt_version: str | None = None,
    source_ip: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        decision_reason=decision_reason,
        policy_version=policy_version,
        model_name=model_name,
        prompt_version=prompt_version,
        correlation_id=correlation_id,
        request_id=request_id,
        source_ip=source_ip,
        success=success,
        error_code=error_code,
        error_message=error_message,
    )
    session.add(event)
    session.flush()
    return event
