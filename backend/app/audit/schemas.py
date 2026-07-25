"""Read-only audit API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: str
    timestamp: datetime
    actor_type: str
    actor_id: str | None
    action: str
    entity_type: str
    entity_id: str
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    decision_reason: str
    policy_version: str | None
    model_name: str | None
    prompt_version: str | None
    correlation_id: str
    request_id: str
    success: bool
    error_code: str | None
    error_message: str | None


class AuditPage(BaseModel):
    items: list[AuditEventResponse]
