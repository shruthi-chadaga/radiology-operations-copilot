from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.scheduling.appointment_management import cancel_appointment, reschedule_appointment
from app.scheduling.booking import BookingRequest, book_appointment
from app.scheduling.models import (
    Appointment,
    AppointmentHistory,
    AppointmentStatus,
    ImagingOrder,
    Slot,
    SlotStatus,
)
from tests.test_booking import create_fixture


def booking_request(referral_id, slot_id, service_id, version: int = 1) -> BookingRequest:  # type: ignore[no-untyped-def]
    return BookingRequest(
        referral_id=referral_id,
        slot_id=slot_id,
        imaging_service_id=service_id,
        expected_slot_version=version,
        actor_id="scheduler-test",
        booking_reason="Accepted deterministic slot recommendation",
        correlation_id="corr-management",
        request_id="req-management",
    )


def test_cancellation_preserves_appointment_and_releases_slot() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, slot, service = create_fixture(session)
        appointment = book_appointment(session, booking_request(referral.id, slot.id, service.id))
        session.commit()

        cancel_appointment(
            session,
            appointment.id,
            reason="Synthetic patient requested another date",
            actor_id="scheduler-test",
            correlation_id="corr-cancel",
            request_id="req-cancel",
        )
        session.commit()
        session.refresh(slot)
        session.refresh(appointment)

        assert appointment.status == AppointmentStatus.CANCELLED
        assert appointment.cancellation_reason == "Synthetic patient requested another date"
        assert slot.status == SlotStatus.FREE
        assert slot.version == 3
        order = session.scalar(
            select(ImagingOrder).where(ImagingOrder.appointment_id == appointment.id)
        )
        assert order is not None and order.status == "cancelled"
        assert len(list(session.scalars(select(AppointmentHistory)))) == 2


def test_reschedule_preserves_old_record_and_books_new_slot() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, old_slot, service = create_fixture(session)
        old_appointment = book_appointment(
            session, booking_request(referral.id, old_slot.id, service.id)
        )
        new_start = datetime(2026, 8, 5, 14, tzinfo=UTC)
        new_slot = Slot(
            schedule_id=old_slot.schedule_id,
            start_time=new_start,
            end_time=new_start + timedelta(minutes=30),
            status=SlotStatus.FREE,
            capacity=1,
            version=1,
        )
        session.add(new_slot)
        session.commit()

        new_appointment = reschedule_appointment(
            session,
            appointment_id=old_appointment.id,
            new_slot_id=new_slot.id,
            expected_new_slot_version=1,
            reason="Earlier deterministic slot accepted",
            actor_id="scheduler-test",
            correlation_id="corr-reschedule",
            request_id="req-reschedule",
        )
        session.commit()
        session.refresh(old_appointment)
        session.refresh(old_slot)
        session.refresh(new_slot)

        assert old_appointment.status == AppointmentStatus.RESCHEDULED
        assert old_slot.status == SlotStatus.FREE
        assert new_slot.status == SlotStatus.BUSY
        assert new_appointment.id != old_appointment.id
        assert new_appointment.referral_id == old_appointment.referral_id
        old_order = session.scalar(
            select(ImagingOrder).where(ImagingOrder.appointment_id == old_appointment.id)
        )
        assert old_order is not None and old_order.status == "rescheduled"
        assert len(list(session.scalars(select(Appointment)))) == 2
