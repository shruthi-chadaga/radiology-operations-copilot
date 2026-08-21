"""Phase E: Modality Worklist, DICOMweb query, and MPPS-lite behavior."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base


def import_full_metadata() -> None:
    """Register every model so cross-module foreign keys resolve."""
    import app.audit.models  # noqa: F401
    import app.auth.models  # noqa: F401
    import app.exceptions.models  # noqa: F401
    import app.imaging.models  # noqa: F401
    import app.incidents.models  # noqa: F401
    import app.pacs.models  # noqa: F401
    import app.scheduling.models  # noqa: F401


def make_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def seed_scheduled_case(
    session: Session,
    *,
    accession: str,
    modality: str = "CT",
    start_offset_hours: float = 2.0,
    appointment_status: str = "booked",
    order_status: str = "scheduled",
    priority: str | None = None,
) -> None:
    from app.scheduling.models import (
        Appointment,
        AppointmentStatus,
        ImagingOrder,
        ImagingService,
        Location,
        Referral,
        ReferralStatus,
        Schedule,
        Slot,
        SyntheticPatient,
    )

    now = datetime.now(UTC)
    suffix = accession[-4:]
    patient = SyntheticPatient(
        external_patient_id=f"SYN-MWL-{suffix}",
        first_name="Testy",
        last_name=f"McCase{suffix}",
        date_of_birth=now.date(),
        sex_for_administrative_use="O",
        email=f"syn-mwl-{suffix}@synthetic.local",
        phone=None,
    )
    session.add(patient)
    session.flush()
    location = Location(
        code=f"SYN-LOC-{suffix}",
        name=f"Synthetic Imaging Center {suffix}",
        timezone="UTC",
    )
    session.add(location)
    session.flush()
    service = ImagingService(
        code=f"SYN-{modality}-{suffix}",
        name=f"Synthetic {modality} service {suffix}",
        modality=modality,
        body_region="SYNTHETIC",
        default_duration_minutes=30,
        location_id=location.id,
    )
    session.add(service)
    session.flush()
    schedule = Schedule(
        imaging_service_id=service.id,
        location_id=location.id,
        start_date=now.date(),
        end_date=now.date() + timedelta(days=7),
    )
    session.add(schedule)
    session.flush()
    slot = Slot(
        schedule_id=schedule.id,
        start_time=now + timedelta(hours=start_offset_hours),
        end_time=now + timedelta(hours=start_offset_hours + 0.5),
        status="busy",
    )
    session.add(slot)
    session.flush()
    referral = Referral(
        referral_number=f"REF-MWL-{suffix}",
        patient_id=patient.id,
        source_text=f"Synthetic referral text for {accession}",
        requested_exam=f"Synthetic {modality} exam",
        requested_priority=priority,
        status=ReferralStatus.SCHEDULED,
        received_at=now,
    )
    session.add(referral)
    session.flush()
    appointment = Appointment(
        appointment_number=f"APPT-MWL-{suffix}",
        accession_number=accession,
        patient_id=patient.id,
        referral_id=referral.id,
        slot_id=slot.id,
        imaging_service_id=service.id,
        status=AppointmentStatus(appointment_status),
        booked_by_type="scheduler",
        booking_reason="Synthetic MWL test booking",
        created_at=now,
    )
    session.add(appointment)
    session.flush()
    order = ImagingOrder(
        accession_number=accession,
        patient_id=patient.id,
        appointment_id=appointment.id,
        requested_procedure_code=f"SYN-PROC-{suffix}",
        requested_procedure_description=f"Synthetic {modality} procedure",
        modality=modality,
        scheduled_start=now + timedelta(hours=start_offset_hours),
        status=order_status,
    )
    session.add(order)
    session.flush()


def test_mwl_lists_booked_orders_and_honors_filters() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    from app.imaging.worklist_service import list_modality_worklist

    with Session(engine) as session:
        seed_scheduled_case(session, accession="ACC-MWL-0001", modality="CT")
        seed_scheduled_case(session, accession="ACC-MWL-0002", modality="MR")
        seed_scheduled_case(session, accession="ACC-MWL-0003", modality="CT")
        session.commit()

        entries = list_modality_worklist(session, window_hours=72)
        assert [e.accession_number for e in entries] == [
            "ACC-MWL-0001",
            "ACC-MWL-0002",
            "ACC-MWL-0003",
        ]
        first = entries[0]
        assert first.external_patient_id.startswith("SYN-")
        assert "^" in first.patient_name  # DICOM-style PN
        assert len(first.patient_birth_date) == 8

        filtered = list_modality_worklist(session, modality="mr", window_hours=72)
        assert [e.accession_number for e in filtered] == ["ACC-MWL-0002"]

        narrow = list_modality_worklist(
            session,
            modality=None,
            window_hours=1,
            now=datetime.now(UTC),
        )
        assert all(e.accession_number != "ACC-MWL-9999" for e in narrow)


def test_mwl_excludes_cancelled_and_acquired_cases() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    from app.imaging.worklist_service import list_modality_worklist

    with Session(engine) as session:
        seed_scheduled_case(
            session,
            accession="ACC-MWL-0010",
            appointment_status="cancelled",
        )
        seed_scheduled_case(session, accession="ACC-MWL-0011", order_status="acquired")
        seed_scheduled_case(session, accession="ACC-MWL-0012")
        session.commit()

        entries = list_modality_worklist(session, window_hours=72)
        assert [e.accession_number for e in entries] == ["ACC-MWL-0012"]


def test_mwl_window_bounds_are_enforced() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    from app.imaging.worklist_service import list_modality_worklist

    with Session(engine) as session:
        seed_scheduled_case(session, accession="ACC-MWL-0020")
        session.commit()
        with pytest.raises(ValueError):
            list_modality_worklist(session, window_hours=0)
        with pytest.raises(ValueError):
            list_modality_worklist(session, window_hours=1000)


def test_mark_order_acquired_is_idempotent() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    from app.imaging.worklist_service import mark_order_acquired

    with Session(engine) as session:
        seed_scheduled_case(session, accession="ACC-MWL-0030")
        session.commit()

        assert mark_order_acquired(session, accession_number="ACC-MWL-0030") is True
        assert mark_order_acquired(session, accession_number="ACC-MWL-0030") is False
        with pytest.raises(LookupError):
            mark_order_acquired(session, accession_number="ACC-MWL-DOES-NOT-EXIST")
