from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.db.base import Base
from app.scheduling.booking import BookingConflict, BookingRequest, book_appointment
from app.scheduling.models import (
    Appointment,
    ImagingOrder,
    ImagingService,
    Location,
    Referral,
    ReferralStatus,
    Schedule,
    Slot,
    SlotStatus,
    SyntheticPatient,
)


def create_fixture(session: Session) -> tuple[Referral, Slot, ImagingService]:
    now = datetime.now(UTC)
    start = (now + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
    patient = SyntheticPatient(
        external_patient_id="SYN-0001",
        first_name="Aster",
        last_name="Example",
        date_of_birth=date(1980, 1, 1),
        email="aster@example.local",
    )
    location = Location(code="central", name="Central Synthetic Imaging", timezone="Europe/Berlin")
    session.add_all([patient, location])
    session.flush()
    service = ImagingService(
        code="CT-ABD",
        name="CT abdomen",
        modality="CT",
        body_region="abdomen",
        default_duration_minutes=30,
        location_id=location.id,
    )
    session.add(service)
    session.flush()
    schedule = Schedule(
        imaging_service_id=service.id,
        location_id=location.id,
        start_date=now.date(),
        end_date=(now + timedelta(days=30)).date(),
        status="active",
    )
    referral = Referral(
        referral_number="REF-0001",
        patient_id=patient.id,
        source_text="Synthetic routine CT abdomen. Authorization approved.",
        requested_exam="CT abdomen",
        modality="CT",
        body_region="abdomen",
        status=ReferralStatus.READY,
        completeness_status="complete",
        extraction_confidence=0.95,
    )
    session.add_all([schedule, referral])
    session.flush()
    slot = Slot(
        schedule_id=schedule.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=SlotStatus.FREE,
        capacity=1,
        version=1,
    )
    session.add(slot)
    session.commit()
    return referral, slot, service


def test_booking_atomically_creates_appointment_order_audit_and_marks_slot_busy() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, slot, service = create_fixture(session)
        appointment = book_appointment(
            session,
            BookingRequest(
                referral_id=referral.id,
                slot_id=slot.id,
                imaging_service_id=service.id,
                expected_slot_version=1,
                actor_id="scheduler-test",
                booking_reason="Highest-ranked eligible slot accepted",
                correlation_id="corr-book-001",
                request_id="req-book-001",
            ),
        )
        session.commit()

        session.refresh(slot)
        order = session.scalar(
            select(ImagingOrder).where(ImagingOrder.appointment_id == appointment.id)
        )
        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.entity_id == str(appointment.id))
        )

        assert slot.status == SlotStatus.BUSY
        assert slot.version == 2
        assert appointment.accession_number.startswith("ACC-")
        assert order is not None
        assert order.accession_number == appointment.accession_number
        assert audit is not None and audit.action == "scheduling.appointment.booked"


def test_second_booking_of_same_slot_is_rejected_without_partial_writes() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, slot, service = create_fixture(session)
        request = BookingRequest(
            referral_id=referral.id,
            slot_id=slot.id,
            imaging_service_id=service.id,
            expected_slot_version=1,
            actor_id="scheduler-test",
            booking_reason="Accepted recommendation",
            correlation_id="corr-book-002",
            request_id="req-book-002",
        )
        book_appointment(session, request)
        session.commit()

        with pytest.raises(BookingConflict) as error:
            book_appointment(session, request)
        session.rollback()

        assert error.value.code == "SLOT_CONFLICT"
        assert (
            session.scalar(select(Appointment).where(Appointment.referral_id == referral.id))
            is not None
        )
        assert len(list(session.scalars(select(Appointment)))) == 1


def test_booking_rejects_a_slot_owned_by_another_service() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, slot, _ = create_fixture(session)
        schedule = session.get(Schedule, slot.schedule_id)
        assert schedule is not None
        other_service = ImagingService(
            code="MR-HEAD",
            name="MR head",
            modality="MR",
            body_region="head",
            default_duration_minutes=30,
            location_id=schedule.location_id,
        )
        session.add(other_service)
        session.commit()

        with pytest.raises(BookingConflict) as error:
            book_appointment(
                session,
                BookingRequest(
                    referral_id=referral.id,
                    slot_id=slot.id,
                    imaging_service_id=other_service.id,
                    expected_slot_version=1,
                    actor_id="scheduler-test",
                    booking_reason="Invalid cross-service request",
                    correlation_id="corr-book-mismatch",
                    request_id="req-book-mismatch",
                ),
            )
        session.rollback()

        assert error.value.code == "BOOKING_SERVICE_MISMATCH"
        assert session.scalar(select(Appointment)) is None
        session.refresh(slot)
        assert slot.status == SlotStatus.FREE


def test_booking_rejects_a_service_that_conflicts_with_the_referral() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, slot, service = create_fixture(session)
        service.modality = "MR"
        service.body_region = "head"
        session.commit()

        with pytest.raises(BookingConflict) as error:
            book_appointment(
                session,
                BookingRequest(
                    referral_id=referral.id,
                    slot_id=slot.id,
                    imaging_service_id=service.id,
                    expected_slot_version=1,
                    actor_id="scheduler-test",
                    booking_reason="Invalid referral-service request",
                    correlation_id="corr-book-referral-mismatch",
                    request_id="req-book-referral-mismatch",
                ),
            )
        session.rollback()

        assert error.value.code == "REFERRAL_SERVICE_MISMATCH"
        assert session.scalar(select(Appointment)) is None


@pytest.mark.parametrize("resource", ["service", "schedule", "location", "past_slot"])
def test_booking_rejects_inactive_or_ineligible_resources(resource: str) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        referral, slot, service = create_fixture(session)
        schedule = session.get(Schedule, slot.schedule_id)
        assert schedule is not None
        location = session.get(Location, schedule.location_id)
        assert location is not None
        if resource == "service":
            service.active = False
        elif resource == "schedule":
            schedule.status = "inactive"
        elif resource == "location":
            location.active = False
        else:
            slot.start_time = datetime.now(UTC) - timedelta(days=1)
            slot.end_time = slot.start_time + timedelta(minutes=30)
        session.commit()

        with pytest.raises(BookingConflict) as error:
            book_appointment(
                session,
                BookingRequest(
                    referral_id=referral.id,
                    slot_id=slot.id,
                    imaging_service_id=service.id,
                    expected_slot_version=1,
                    actor_id="scheduler-test",
                    booking_reason="Ineligible resource request",
                    correlation_id=f"corr-book-{resource}",
                    request_id=f"req-book-{resource}",
                ),
            )

        assert error.value.code == "INELIGIBLE_BOOKING_RESOURCE"
        assert session.scalar(select(Appointment)) is None
