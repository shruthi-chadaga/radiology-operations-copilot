"""MPPS-lite: deterministic modality procedure step lifecycle tracking.

Mirrors the shape of DICOM MPPS (N-CREATE / N-SET) without any network
protocol: a step starts once, ends exactly once, and every transition is
persisted evidence. No PACS or DICOM mutation occurs here.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.pacs.models import ProcedureStep, ProcedureStepStatus
from app.scheduling.models import ImagingOrder


class ProcedureStepError(Exception):
    """Expected procedure step transition failure."""

    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _normalize_status(value: object) -> ProcedureStepStatus:
    if isinstance(value, ProcedureStepStatus):
        return value
    return ProcedureStepStatus(str(value))


def _step_response(step: ProcedureStep) -> dict[str, object]:
    status_value = _normalize_status(step.status)
    return {
        "id": str(step.id),
        "accession_number": step.accession_number,
        "step_number": step.step_number,
        "status": status_value.value,
        "started_by": step.started_by,
        "started_at": step.started_at.isoformat(),
        "ended_at": step.ended_at.isoformat() if step.ended_at else None,
        "end_reason": step.end_reason,
        "performed_series_count": step.performed_series_count,
    }


def start_step(
    session: Session,
    *,
    accession_number: str,
    started_by: str,
    correlation_id: str | None = None,
) -> dict[str, object]:
    """Start one procedure step for an accession (MPPS N-CREATE equivalent)."""
    order = session.scalar(
        select(ImagingOrder).where(ImagingOrder.accession_number == accession_number)
    )
    if order is None:
        raise ProcedureStepError("No imaging order exists for this accession", status_code=404)
    active = session.scalar(
        select(ProcedureStep).where(
            ProcedureStep.accession_number == accession_number,
            ProcedureStep.status == ProcedureStepStatus.IN_PROGRESS,
        )
    )
    if active is not None:
        raise ProcedureStepError(
            "A procedure step is already in progress for this accession",
            status_code=409,
        )
    step_number = (
        int(
            session.scalar(
                select(func.count())
                .select_from(ProcedureStep)
                .where(ProcedureStep.accession_number == accession_number)
            )
            or 0
        )
        + 1
    )
    step = ProcedureStep(
        accession_number=accession_number,
        step_number=step_number,
        status=ProcedureStepStatus.IN_PROGRESS,
        started_by=started_by,
    )
    session.add(step)
    session.flush()
    append_audit_event(
        session,
        actor=AuditActor("user", started_by),
        action="imaging.procedure_step.started",
        entity_type="procedure_step",
        entity_id=str(step.id),
        decision_reason="Modality procedure step started for acquisition",
        correlation_id=correlation_id or f"step-{step.id}",
        request_id=correlation_id or f"step-{step.id}",
        success=True,
        after_state={
            "accession_number": step.accession_number,
            "step_number": step.step_number,
            "status": ProcedureStepStatus.IN_PROGRESS.value,
        },
    )
    session.flush()
    return _step_response(step)


def complete_step(
    session: Session,
    *,
    step_id: uuid.UUID,
    performed_series_count: int,
    completed_by: str,
) -> dict[str, object]:
    step = session.scalar(
        select(ProcedureStep)
        .where(ProcedureStep.id == step_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if step is None:
        raise ProcedureStepError("Procedure step not found", status_code=404)
    if _normalize_status(step.status) != ProcedureStepStatus.IN_PROGRESS:
        raise ProcedureStepError("Only an in-progress step can be completed", status_code=409)
    if not 1 <= performed_series_count <= 1000:
        raise ProcedureStepError(
            "performed_series_count must be between 1 and 1000", status_code=422
        )
    step.status = ProcedureStepStatus.COMPLETED
    step.performed_series_count = performed_series_count
    step.ended_at = datetime.now(UTC)
    append_audit_event(
        session,
        actor=AuditActor("user", completed_by),
        action="imaging.procedure_step.completed",
        entity_type="procedure_step",
        entity_id=str(step.id),
        decision_reason="Modality procedure step completed with performed series count",
        correlation_id=f"step-{step.id}",
        request_id=f"step-{step.id}",
        success=True,
        after_state={
            "status": ProcedureStepStatus.COMPLETED.value,
            "performed_series_count": performed_series_count,
        },
    )
    session.flush()
    return _step_response(step)


def discontinue_step(
    session: Session,
    *,
    step_id: uuid.UUID,
    reason: str,
    discontinued_by: str,
) -> dict[str, object]:
    step = session.scalar(
        select(ProcedureStep)
        .where(ProcedureStep.id == step_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if step is None:
        raise ProcedureStepError("Procedure step not found", status_code=404)
    if _normalize_status(step.status) != ProcedureStepStatus.IN_PROGRESS:
        raise ProcedureStepError("Only an in-progress step can be discontinued", status_code=409)
    clean_reason = reason.strip()
    if not clean_reason:
        raise ProcedureStepError("A discontinuation reason is required", status_code=422)
    step.status = ProcedureStepStatus.DISCONTINUED
    step.end_reason = clean_reason[:300]
    step.ended_at = datetime.now(UTC)
    append_audit_event(
        session,
        actor=AuditActor("user", discontinued_by),
        action="imaging.procedure_step.discontinued",
        entity_type="procedure_step",
        entity_id=str(step.id),
        decision_reason="Modality procedure step discontinued before completion",
        correlation_id=f"step-{step.id}",
        request_id=f"step-{step.id}",
        success=True,
        after_state={
            "status": ProcedureStepStatus.DISCONTINUED.value,
            "reason": clean_reason[:300],
        },
    )
    session.flush()
    return _step_response(step)


def list_steps(session: Session, *, limit: int = 200) -> list[dict[str, object]]:
    steps = list(
        session.scalars(
            select(ProcedureStep)
            .order_by(ProcedureStep.started_at.desc(), ProcedureStep.id)
            .limit(min(limit, 500))
        )
    )
    return [_step_response(step) for step in steps]
