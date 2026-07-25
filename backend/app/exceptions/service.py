"""Deterministic synchronization of validation results to the human exception queue."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions.models import ExceptionCase
from app.scheduling.validation import ValidationResult


def sync_referral_exception(
    session: Session, source_entity_id: str, result: ValidationResult
) -> ExceptionCase | None:
    existing = session.scalar(
        select(ExceptionCase).where(
            ExceptionCase.domain == "scheduling",
            ExceptionCase.source_entity_type == "referral",
            ExceptionCase.source_entity_id == source_entity_id,
            ExceptionCase.status == "open",
        )
    )
    if result.issues:
        if existing is not None:
            existing.category = result.issues[0].code
            existing.description = "; ".join(issue.message for issue in result.issues)
            return existing
        case = ExceptionCase(
            exception_number=f"EXC-{uuid.uuid4().hex[:10].upper()}",
            domain="scheduling",
            category=result.issues[0].code,
            severity="medium",
            status="open",
            title="Referral needs human review",
            description="; ".join(issue.message for issue in result.issues),
            source_entity_type="referral",
            source_entity_id=source_entity_id,
            assigned_role="scheduler",
            suggested_action="Review and correct administrative referral fields",
        )
        session.add(case)
        session.flush()
        return case
    if existing is not None:
        existing.status = "resolved"
        existing.resolved_at = datetime.now(UTC)
        existing.resolution = "Deterministic referral validation passed"
    return None
