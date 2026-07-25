"""Scheduling workflow API with strict schemas, deterministic rules, RBAC, and audit."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.mock_provider import MockAIProvider
from app.ai.schemas import ReferralExtraction
from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.config import get_settings
from app.db.session import get_db
from app.exceptions.service import sync_referral_exception
from app.scheduling.appointment_management import cancel_appointment, reschedule_appointment
from app.scheduling.booking import BookingConflict, BookingRequest, book_appointment
from app.scheduling.models import (
    Appointment,
    ImagingService,
    Location,
    Referral,
    ReferralFieldExtraction,
    ReferralStatus,
    Schedule,
    Slot,
    SlotStatus,
    SyntheticPatient,
)
from app.scheduling.schemas import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    ReferralCreate,
    ReferralPage,
    ReferralResponse,
    SlotRecommendationPage,
    SlotRecommendationRequest,
    SlotRecommendationResponse,
    ValidationIssueResponse,
    ValidationResponse,
)
from app.scheduling.slot_ranking import SlotCandidate, SlotPreferences, rank_slots
from app.scheduling.validation import ReferralValidationContext, validate_referral

router = APIRouter(tags=["scheduling"])
provider = MockAIProvider()
settings = get_settings()
_SCHEDULING_ROLES = {Role.SCHEDULER, Role.OPERATIONS_MANAGER}


def _authorize(user: User) -> None:
    if user.role not in _SCHEDULING_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _referral_response(referral: Referral) -> ReferralResponse:
    return ReferralResponse(
        id=str(referral.id),
        referral_number=referral.referral_number,
        patient_id=str(referral.patient_id),
        source_text=referral.source_text,
        requested_exam=referral.requested_exam,
        modality=referral.modality,
        body_region=referral.body_region,
        status=referral.status.value,
        completeness_status=referral.completeness_status,
        extraction_confidence=referral.extraction_confidence,
    )


def _request_ids(request: Request) -> tuple[str, str]:
    request_id = request.headers.get("x-request-id", f"local-{uuid.uuid4().hex[:12]}")
    return request_id, request.headers.get("x-correlation-id", request_id)


def _audit_denial(
    db: Session,
    *,
    user: User,
    action: str,
    entity_type: str,
    entity_id: str,
    exc: ValueError | BookingConflict,
    request_id: str,
    correlation_id: str,
) -> None:
    error_code = exc.code if isinstance(exc, BookingConflict) else "INVALID_REQUEST"
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        decision_reason="Deterministic scheduling policy denied the requested transition",
        correlation_id=correlation_id,
        request_id=request_id,
        success=False,
        policy_version="scheduling-policy-v1",
        error_code=error_code,
        error_message=str(exc),
    )
    db.commit()


def _appointment_response(appointment: Appointment) -> AppointmentResponse:
    return AppointmentResponse(
        id=str(appointment.id),
        appointment_number=appointment.appointment_number,
        accession_number=appointment.accession_number,
        referral_id=str(appointment.referral_id),
        slot_id=str(appointment.slot_id),
        status=appointment.status.value,
    )


@router.get("/referrals", response_model=ReferralPage)
def list_referrals(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReferralPage:
    _authorize(user)
    referrals = db.scalars(select(Referral).order_by(Referral.received_at.desc()).limit(100))
    return ReferralPage(items=[_referral_response(referral) for referral in referrals])


@router.get("/referrals/{referral_id}", response_model=ReferralResponse)
def get_referral(
    referral_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReferralResponse:
    _authorize(user)
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    return _referral_response(referral)


@router.post("/referrals", response_model=ReferralResponse, status_code=status.HTTP_201_CREATED)
def create_referral(
    payload: ReferralCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReferralResponse:
    _authorize(user)
    try:
        patient_id = uuid.UUID(payload.patient_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid synthetic patient ID") from exc
    if db.get(SyntheticPatient, patient_id) is None:
        raise HTTPException(status_code=404, detail="Synthetic patient not found")
    referral = Referral(
        referral_number=f"REF-{uuid.uuid4().hex[:10].upper()}",
        patient_id=patient_id,
        source_text=payload.source_text,
        source_type="text",
        status=ReferralStatus.NEW,
        completeness_status="not_reviewed",
    )
    db.add(referral)
    db.flush()
    request_id, correlation_id = _request_ids(request)
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="scheduling.referral.created",
        entity_type="referral",
        entity_id=str(referral.id),
        decision_reason="Synthetic referral entered by authorized scheduling user",
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        after_state={"referral_number": referral.referral_number, "synthetic_only": True},
    )
    db.commit()
    return _referral_response(referral)


@router.post("/referrals/{referral_id}/extract", response_model=ReferralExtraction)
def extract_referral(
    referral_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReferralExtraction:
    _authorize(user)
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    extraction = provider.extract_referral(referral.source_text)
    fields = {
        "requested_exam": extraction.requested_exam,
        "modality": extraction.modality,
        "body_region": extraction.body_region,
        "laterality": extraction.laterality,
        "requested_priority": extraction.explicit_priority,
        "preferred_location": extraction.preferred_location,
        "contrast_indicator": extraction.contrast_indicator,
        "sedation_indicator": extraction.sedation_indicator,
        "authorization_status": extraction.authorization_status,
    }
    current_fields = {
        row.field_name: row
        for row in db.scalars(
            select(ReferralFieldExtraction).where(
                ReferralFieldExtraction.referral_id == referral.id
            )
        )
    }
    for name, field in fields.items():
        current = current_fields.get(name)
        if current is None:
            current = ReferralFieldExtraction(
                referral_id=referral.id,
                field_name=name,
                accepted_value=field.value,
                model_name=extraction.model_name,
                prompt_version=extraction.prompt_version,
            )
            db.add(current)
        current.extracted_value = field.value
        current.confidence = field.confidence
        current.source_excerpt = field.source_excerpt
        current.model_name = extraction.model_name
        current.prompt_version = extraction.prompt_version
        if current.corrected_by is None:
            current.accepted_value = field.value
        setattr(referral, name, current.accepted_value)
    confidences = [field.confidence for field in fields.values() if field.value is not None]
    referral.extraction_confidence = min(confidences) if confidences else 0.0
    referral.status = (
        ReferralStatus.REVIEW if extraction.requires_human_review else ReferralStatus.NEW
    )
    request_id, correlation_id = _request_ids(request)
    append_audit_event(
        db,
        actor=AuditActor("ai", extraction.model_name),
        action="scheduling.referral.extracted",
        entity_type="referral",
        entity_id=str(referral.id),
        decision_reason="Structured administrative extraction; no clinical inference",
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        model_name=extraction.model_name,
        prompt_version=extraction.prompt_version,
        after_state=extraction.model_dump(mode="json"),
    )
    db.commit()
    return extraction


@router.post("/referrals/{referral_id}/validate", response_model=ValidationResponse)
def validate_referral_endpoint(
    referral_id: uuid.UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ValidationResponse:
    _authorize(user)
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    extraction = provider.extract_referral(referral.source_text)
    service = db.scalar(
        select(ImagingService).where(
            ImagingService.modality == extraction.modality.value,
            ImagingService.body_region == extraction.body_region.value,
            ImagingService.active.is_(True),
        )
    )
    location_active = True
    if extraction.preferred_location.value:
        location_active = (
            db.scalar(
                select(Location.active).where(
                    func.lower(Location.name) == extraction.preferred_location.value.lower()
                )
            )
            is True
        )
    result = validate_referral(
        ReferralValidationContext(
            patient_id=str(referral.patient_id),
            extraction=extraction,
            imaging_service_exists=service is not None,
            requested_location_active=location_active,
            identity_conflict=False,
            low_confidence_threshold=settings.low_confidence_threshold,
        )
    )
    referral.completeness_status = "complete" if result.is_complete else "incomplete"
    referral.status = ReferralStatus.READY if result.is_complete else ReferralStatus.EXCEPTION
    exception = sync_referral_exception(db, str(referral.id), result)
    request_id, correlation_id = _request_ids(request)
    append_audit_event(
        db,
        actor=AuditActor("system", None),
        action="scheduling.referral.validated",
        entity_type="referral",
        entity_id=str(referral.id),
        decision_reason="Deterministic referral completeness policy",
        correlation_id=correlation_id,
        request_id=request_id,
        success=result.is_complete,
        policy_version="referral-validation-v1",
        after_state={"issues": [issue.code for issue in result.issues]},
    )
    if exception is not None:
        append_audit_event(
            db,
            actor=AuditActor("system", None),
            action="scheduling.exception.created_or_updated",
            entity_type="exception_case",
            entity_id=str(exception.id),
            decision_reason="Referral failed deterministic validation",
            correlation_id=correlation_id,
            request_id=request_id,
            success=True,
            policy_version="referral-validation-v1",
            after_state={"category": exception.category, "status": exception.status},
        )
    db.commit()
    return ValidationResponse(
        is_complete=result.is_complete,
        requires_human_review=result.requires_human_review,
        issues=[ValidationIssueResponse.from_issue(issue) for issue in result.issues],
    )


@router.post("/referrals/{referral_id}/slot-recommendations", response_model=SlotRecommendationPage)
def slot_recommendations(
    referral_id: uuid.UUID,
    payload: SlotRecommendationRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SlotRecommendationPage:
    _authorize(user)
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    if referral.status != ReferralStatus.READY or not referral.modality:
        raise HTTPException(status_code=409, detail="Referral is not ready for slot search")
    service = db.scalar(
        select(ImagingService).where(
            ImagingService.modality == referral.modality,
            ImagingService.body_region == referral.body_region,
            ImagingService.active.is_(True),
        )
    )
    rows: list[tuple[Slot, Location]] = []
    if service is not None:
        rows = [
            (slot, location)
            for slot, location in db.execute(
                select(Slot, Location)
                .join(Schedule, Slot.schedule_id == Schedule.id)
                .join(Location, Schedule.location_id == Location.id)
                .where(
                    Schedule.imaging_service_id == service.id,
                    Schedule.status == "active",
                    Slot.status == SlotStatus.FREE,
                    Location.active.is_(True),
                )
            )
        ]
    by_id = {str(slot.id): slot for slot, _ in rows}
    ranked = (
        []
        if service is None
        else rank_slots(
            [
                SlotCandidate(str(slot.id), slot.start_time, location.code, service.modality)
                for slot, location in rows
            ],
            SlotPreferences(
                modality=referral.modality,
                preferred_location_code=payload.preferred_location_code,
                preferred_time_of_day=payload.preferred_time_of_day,
            ),
        )
    )
    items = [
        SlotRecommendationResponse(
            slot_id=item.slot_id,
            start_time=item.start_time,
            score=item.score,
            explanation=item.explanation,
            version=by_id[item.slot_id].version,
        )
        for item in ranked[:3]
    ]
    request_id, correlation_id = _request_ids(request)
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="scheduling.slot_recommendations.generated",
        entity_type="referral",
        entity_id=str(referral.id),
        decision_reason="Deterministic slot ranking completed",
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        policy_version="slot-ranking-v1",
        after_state={
            "preferred_location_code": payload.preferred_location_code,
            "preferred_time_of_day": payload.preferred_time_of_day,
            "recommendations": [{"slot_id": item.slot_id, "score": item.score} for item in items],
        },
    )
    db.commit()
    return SlotRecommendationPage(items=items)


@router.post(
    "/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED
)
def create_appointment(
    payload: AppointmentCreate,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AppointmentResponse:
    _authorize(user)
    request_id, correlation_id = _request_ids(request)
    try:
        appointment = book_appointment(
            db,
            BookingRequest(
                referral_id=uuid.UUID(payload.referral_id),
                slot_id=uuid.UUID(payload.slot_id),
                imaging_service_id=uuid.UUID(payload.imaging_service_id),
                expected_slot_version=payload.expected_slot_version,
                actor_id=str(user.id),
                booking_reason=payload.booking_reason,
                correlation_id=correlation_id,
                request_id=request_id,
            ),
        )
        db.commit()
    except (ValueError, BookingConflict) as exc:
        db.rollback()
        _audit_denial(
            db,
            user=user,
            action="scheduling.appointment.booking_denied",
            entity_type="referral",
            entity_id=payload.referral_id,
            exc=exc,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        detail = str(exc)
        if isinstance(exc, BookingConflict):
            detail = f"{exc.code}: {exc}"
        raise HTTPException(status_code=409, detail=detail) from exc
    return _appointment_response(appointment)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment_endpoint(
    appointment_id: uuid.UUID,
    payload: AppointmentCancel,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AppointmentResponse:
    _authorize(user)
    request_id, correlation_id = _request_ids(request)
    try:
        appointment = cancel_appointment(
            db,
            appointment_id,
            reason=payload.reason,
            actor_id=str(user.id),
            correlation_id=correlation_id,
            request_id=request_id,
        )
        db.commit()
    except BookingConflict as exc:
        db.rollback()
        _audit_denial(
            db,
            user=user,
            action="scheduling.appointment.cancellation_denied",
            entity_type="appointment",
            entity_id=str(appointment_id),
            exc=exc,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=409, detail=f"{exc.code}: {exc}") from exc
    return _appointment_response(appointment)


@router.post("/appointments/{appointment_id}/reschedule", response_model=AppointmentResponse)
def reschedule_appointment_endpoint(
    appointment_id: uuid.UUID,
    payload: AppointmentReschedule,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AppointmentResponse:
    _authorize(user)
    request_id, correlation_id = _request_ids(request)
    try:
        appointment = reschedule_appointment(
            db,
            appointment_id=appointment_id,
            new_slot_id=uuid.UUID(payload.new_slot_id),
            expected_new_slot_version=payload.expected_new_slot_version,
            reason=payload.reason,
            actor_id=str(user.id),
            correlation_id=correlation_id,
            request_id=request_id,
        )
        db.commit()
    except (ValueError, BookingConflict) as exc:
        db.rollback()
        _audit_denial(
            db,
            user=user,
            action="scheduling.appointment.reschedule_denied",
            entity_type="appointment",
            entity_id=str(appointment_id),
            exc=exc,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        detail = str(exc)
        if isinstance(exc, BookingConflict):
            detail = f"{exc.code}: {exc}"
        raise HTTPException(status_code=409, detail=detail) from exc
    return _appointment_response(appointment)
