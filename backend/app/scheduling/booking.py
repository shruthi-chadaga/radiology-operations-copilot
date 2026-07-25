"""Transactional appointment booking with slot locking and deterministic audit."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.scheduling.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    ImagingOrder,
    ImagingService,
    Location,
    Referral,
    ReferralStatus,
    Schedule,
    Slot,
    SlotStatus,
)


class BookingConflict(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BookingRequest:
    referral_id: uuid.UUID
    slot_id: uuid.UUID
    imaging_service_id: uuid.UUID
    expected_slot_version: int
    actor_id: str
    booking_reason: str
    correlation_id: str
    request_id: str


def book_appointment(session: Session, request: BookingRequest) -> Appointment:
    referral = session.scalar(
        select(Referral).where(Referral.id == request.referral_id).with_for_update()
    )
    slot = session.scalar(select(Slot).where(Slot.id == request.slot_id).with_for_update())
    if (
        slot is None
        or slot.status != SlotStatus.FREE
        or slot.version != request.expected_slot_version
    ):
        raise BookingConflict("SLOT_CONFLICT", "The slot is no longer available")

    service = session.get(ImagingService, request.imaging_service_id)
    if referral is None or service is None:
        raise BookingConflict("INVALID_BOOKING_REFERENCE", "Referral or service was not found")
    if referral.status != ReferralStatus.READY:
        raise BookingConflict("REFERRAL_NOT_READY", "Referral requires review before booking")
    schedule = session.get(Schedule, slot.schedule_id)
    if schedule is None or schedule.imaging_service_id != service.id:
        raise BookingConflict(
            "BOOKING_SERVICE_MISMATCH", "The slot does not belong to the requested service"
        )
    if service.modality != referral.modality or service.body_region != referral.body_region:
        raise BookingConflict(
            "REFERRAL_SERVICE_MISMATCH",
            "The requested service does not match the reviewed referral",
        )
    location = session.get(Location, schedule.location_id)
    slot_start = slot.start_time
    if slot_start.tzinfo is None:
        slot_start = slot_start.replace(tzinfo=UTC)
    if (
        not service.active
        or schedule.status != "active"
        or location is None
        or not location.active
        or not (schedule.start_date <= slot_start.date() <= schedule.end_date)
        or slot_start <= datetime.now(UTC)
    ):
        raise BookingConflict(
            "INELIGIBLE_BOOKING_RESOURCE",
            "The service, location, schedule, or slot is not eligible for booking",
        )

    active = session.scalar(
        select(Appointment).where(
            Appointment.referral_id == referral.id,
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED]),
        )
    )
    if active is not None:
        raise BookingConflict(
            "ACTIVE_APPOINTMENT_EXISTS", "An active appointment already exists for this referral"
        )

    token = uuid.uuid4().hex[:12].upper()
    appointment = Appointment(
        appointment_number=f"APT-{token}",
        accession_number=f"ACC-{token}",
        patient_id=referral.patient_id,
        referral_id=referral.id,
        slot_id=slot.id,
        imaging_service_id=service.id,
        status=AppointmentStatus.BOOKED,
        booked_by_type="user",
        booking_reason=request.booking_reason,
        confirmation_status="pending",
    )
    session.add(appointment)
    session.flush()
    session.add(
        ImagingOrder(
            accession_number=appointment.accession_number,
            patient_id=referral.patient_id,
            appointment_id=appointment.id,
            requested_procedure_code=service.code,
            requested_procedure_description=service.name,
            modality=service.modality,
            scheduled_start=slot.start_time,
            status="scheduled",
        )
    )
    session.add(
        AppointmentHistory(
            appointment_id=appointment.id,
            previous_status=None,
            new_status=AppointmentStatus.BOOKED.value,
            actor_id=request.actor_id,
            reason=request.booking_reason,
        )
    )
    slot.status = SlotStatus.BUSY
    slot.version += 1
    referral.status = ReferralStatus.SCHEDULED
    append_audit_event(
        session,
        actor=AuditActor("user", request.actor_id),
        action="scheduling.appointment.booked",
        entity_type="appointment",
        entity_id=str(appointment.id),
        decision_reason=request.booking_reason,
        correlation_id=request.correlation_id,
        request_id=request.request_id,
        success=True,
        after_state={
            "appointment_number": appointment.appointment_number,
            "accession_number": appointment.accession_number,
            "slot_id": str(slot.id),
        },
    )
    session.flush()
    return appointment
