"""Cancellation and rescheduling preserve history and use locked slot transitions."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.scheduling.booking import BookingConflict, BookingRequest, book_appointment
from app.scheduling.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    ImagingOrder,
    Referral,
    ReferralStatus,
    Slot,
    SlotStatus,
)


def cancel_appointment(
    session: Session,
    appointment_id: uuid.UUID,
    *,
    reason: str,
    actor_id: str,
    correlation_id: str,
    request_id: str,
) -> Appointment:
    appointment = session.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if appointment is None or appointment.status not in {
        AppointmentStatus.BOOKED,
        AppointmentStatus.CONFIRMED,
    }:
        raise BookingConflict("APPOINTMENT_NOT_ACTIVE", "Appointment is not active")
    slot = session.scalar(select(Slot).where(Slot.id == appointment.slot_id).with_for_update())
    referral = session.get(Referral, appointment.referral_id)
    if slot is None or referral is None:
        raise BookingConflict("INVALID_BOOKING_REFERENCE", "Appointment references are incomplete")
    order = session.scalar(
        select(ImagingOrder).where(ImagingOrder.appointment_id == appointment.id).with_for_update()
    )
    if order is None:
        raise BookingConflict("ORDER_NOT_FOUND", "Appointment order was not found")

    previous = appointment.status
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = datetime.now(UTC)
    appointment.cancellation_reason = reason
    slot.status = SlotStatus.FREE
    slot.version += 1
    referral.status = ReferralStatus.READY
    order.status = "cancelled"
    session.add(
        AppointmentHistory(
            appointment_id=appointment.id,
            previous_status=previous.value,
            new_status=AppointmentStatus.CANCELLED.value,
            actor_id=actor_id,
            reason=reason,
        )
    )
    append_audit_event(
        session,
        actor=AuditActor("user", actor_id),
        action="scheduling.appointment.cancelled",
        entity_type="appointment",
        entity_id=str(appointment.id),
        decision_reason=reason,
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        before_state={"status": previous.value, "slot_id": str(slot.id)},
        after_state={"status": AppointmentStatus.CANCELLED.value, "slot_released": True},
    )
    session.flush()
    return appointment


def reschedule_appointment(
    session: Session,
    *,
    appointment_id: uuid.UUID,
    new_slot_id: uuid.UUID,
    expected_new_slot_version: int,
    reason: str,
    actor_id: str,
    correlation_id: str,
    request_id: str,
) -> Appointment:
    old = session.scalar(
        select(Appointment).where(Appointment.id == appointment_id).with_for_update()
    )
    if old is None or old.status not in {
        AppointmentStatus.BOOKED,
        AppointmentStatus.CONFIRMED,
    }:
        raise BookingConflict("APPOINTMENT_NOT_ACTIVE", "Appointment is not active")
    old_slot = session.scalar(select(Slot).where(Slot.id == old.slot_id).with_for_update())
    new_slot = session.scalar(select(Slot).where(Slot.id == new_slot_id).with_for_update())
    referral = session.get(Referral, old.referral_id)
    if old_slot is None or referral is None:
        raise BookingConflict("INVALID_BOOKING_REFERENCE", "Appointment references are incomplete")
    old_order = session.scalar(
        select(ImagingOrder).where(ImagingOrder.appointment_id == old.id).with_for_update()
    )
    if old_order is None:
        raise BookingConflict("ORDER_NOT_FOUND", "Appointment order was not found")
    if (
        new_slot is None
        or new_slot.status != SlotStatus.FREE
        or new_slot.version != expected_new_slot_version
    ):
        raise BookingConflict("SLOT_CONFLICT", "The new slot is no longer available")

    previous = old.status
    old.status = AppointmentStatus.RESCHEDULED
    old_slot.status = SlotStatus.FREE
    old_slot.version += 1
    referral.status = ReferralStatus.READY
    old_order.status = "rescheduled"
    session.add(
        AppointmentHistory(
            appointment_id=old.id,
            previous_status=previous.value,
            new_status=AppointmentStatus.RESCHEDULED.value,
            actor_id=actor_id,
            reason=reason,
        )
    )
    append_audit_event(
        session,
        actor=AuditActor("user", actor_id),
        action="scheduling.appointment.rescheduled_from",
        entity_type="appointment",
        entity_id=str(old.id),
        decision_reason=reason,
        correlation_id=correlation_id,
        request_id=request_id,
        success=True,
        before_state={"status": previous.value, "slot_id": str(old_slot.id)},
        after_state={"status": AppointmentStatus.RESCHEDULED.value, "slot_released": True},
    )
    session.flush()
    return book_appointment(
        session,
        BookingRequest(
            referral_id=old.referral_id,
            slot_id=new_slot.id,
            imaging_service_id=old.imaging_service_id,
            expected_slot_version=expected_new_slot_version,
            actor_id=actor_id,
            booking_reason=reason,
            correlation_id=correlation_id,
            request_id=request_id,
        ),
    )
