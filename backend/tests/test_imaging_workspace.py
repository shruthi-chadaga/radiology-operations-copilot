from datetime import UTC, date, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.imaging.models import ImagingWorklistItem, ImagingWorklistStatus
from app.imaging.service import build_timeline, synchronize_worklist
from app.pacs.models import PacsNode, PacsStudy
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
    SlotStatus,
    SyntheticPatient,
)


def setup_session() -> tuple[Session, SyntheticPatient, Appointment, PacsStudy]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    patient = SyntheticPatient(
        external_patient_id="SYN-IMAGING-1",
        first_name="Aster",
        last_name="Example",
        date_of_birth=date(1980, 1, 1),
        email="aster@example.local",
    )
    location = Location(code="imaging", name="Synthetic Imaging", timezone="UTC")
    session.add_all([patient, location])
    session.flush()
    service = ImagingService(
        code="XR-CHEST",
        name="Chest radiograph",
        modality="DX",
        body_region="chest",
        default_duration_minutes=15,
        location_id=location.id,
    )
    session.add(service)
    session.flush()
    schedule = Schedule(
        imaging_service_id=service.id,
        location_id=location.id,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    session.add(schedule)
    session.flush()
    slot = Slot(
        schedule_id=schedule.id,
        start_time=datetime(2026, 8, 7, 9, tzinfo=UTC),
        end_time=datetime(2026, 8, 7, 9, 15, tzinfo=UTC),
        status=SlotStatus.BUSY,
    )
    referral = Referral(
        referral_number="REF-IMAGING-1",
        patient_id=patient.id,
        source_text="Synthetic urgent chest radiograph",
        requested_exam="Chest radiograph",
        modality="DX",
        requested_priority="urgent",
        status=ReferralStatus.SCHEDULED,
        completeness_status="complete",
        received_at=datetime(2026, 8, 6, 8, tzinfo=UTC),
    )
    session.add_all([slot, referral])
    session.flush()
    appointment = Appointment(
        appointment_number="APT-IMAGING-1",
        accession_number="ACC-IMAGING-1",
        patient_id=patient.id,
        referral_id=referral.id,
        slot_id=slot.id,
        imaging_service_id=service.id,
        status=AppointmentStatus.BOOKED,
        booked_by_type="scheduler",
        booking_reason="Synthetic test booking",
        created_at=datetime(2026, 8, 6, 9, tzinfo=UTC),
    )
    session.add(appointment)
    session.flush()
    order = ImagingOrder(
        accession_number=appointment.accession_number,
        patient_id=patient.id,
        appointment_id=appointment.id,
        requested_procedure_code="XR-CHEST",
        requested_procedure_description="Synthetic chest radiograph",
        modality="DX",
        scheduled_start=slot.start_time,
    )
    node = PacsNode(
        name="Imaging Source",
        node_type="source",
        base_url="http://source:8042",
        dicom_ae_title="SOURCE",
        dicom_host="source",
        dicom_port=4242,
        adapter_key="source-imaging",
    )
    session.add_all([order, node])
    session.flush()
    study = PacsStudy(
        node_id=node.id,
        orthanc_study_id="orthanc-imaging-1",
        study_instance_uid="1.2.840.synthetic.imaging.1",
        accession_number=appointment.accession_number,
        patient_id=patient.external_patient_id,
        study_date="20260807",
        study_description="Synthetic chest radiograph",
        modality="DX",
        patient_name="Example^Aster",
        series_count=1,
        instance_count=2,
        metadata_json={"synthetic": True},
        last_seen_at=datetime(2026, 8, 7, 9, 20, tzinfo=UTC),
    )
    session.add(study)
    session.commit()
    return session, patient, appointment, study


def test_worklist_projection_links_schedule_to_received_study_and_priority() -> None:
    session, patient, appointment, study = setup_session()
    try:
        assert synchronize_worklist(session) == 1
        session.commit()
        item = session.scalar(
            select(ImagingWorklistItem).where(ImagingWorklistItem.pacs_study_id == study.id)
        )
        assert item is not None
        assert item.patient_id == patient.id
        assert item.appointment_id == appointment.id
        assert item.workflow_status == ImagingWorklistStatus.READY_FOR_REVIEW
        assert item.priority.value == "urgent"
        assert item.pacs_patient_id == patient.external_patient_id
    finally:
        session.close()


def test_worklist_sync_is_idempotent_and_preserves_in_review_state() -> None:
    session, _, _, study = setup_session()
    try:
        synchronize_worklist(session)
        item = session.scalar(
            select(ImagingWorklistItem).where(ImagingWorklistItem.pacs_study_id == study.id)
        )
        assert item is not None
        item.workflow_status = ImagingWorklistStatus.IN_REVIEW
        session.commit()
        synchronize_worklist(session)
        session.commit()
        items = list(session.scalars(select(ImagingWorklistItem)))
        assert len(items) == 1
        assert items[0].workflow_status == ImagingWorklistStatus.IN_REVIEW
    finally:
        session.close()


def test_patient_timeline_is_newest_first_and_contains_referral_appointment_study() -> None:
    session, patient, _, _ = setup_session()
    try:
        events = build_timeline(session, patient.id)
        assert [event["event_type"] for event in events] == [
            "study",
            "appointment",
            "referral",
        ]
        assert events[0]["label"] == "Study received"
    finally:
        session.close()
