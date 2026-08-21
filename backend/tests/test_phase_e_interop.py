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


# ---------------------------------------------------------------------------
# API surfaces: MWL endpoint + DICOMweb-style study query
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.models import Role, User  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.pacs.models import PacsNode, PacsStudy  # noqa: E402


def seed_received_study(
    session: Session,
    *,
    accession: str,
    modality: str = "CT",
    patient_id: str = "SYN-QIDO-0001",
) -> PacsStudy:
    node = session.query(PacsNode).filter_by(adapter_key="qido-source").first()
    if node is None:
        node = PacsNode(
            name="QIDO Source Orthanc",
            node_type="source",
            base_url="http://qido-source:8042",
            dicom_ae_title="QIDO_SOURCE",
            dicom_host="qido-source",
            dicom_port=4242,
            adapter_key="qido-source",
        )
        session.add(node)
        session.flush()
    study = PacsStudy(
        node_id=node.id,
        orthanc_study_id=f"qido-{accession[-4:]}",
        study_instance_uid=f"1.2.826.0.1.3680043.10.9999.{accession[-4:]}",
        accession_number=accession,
        patient_id=patient_id,
        patient_name=f"SyntheticQido{accession[-4:]}^Example",
        study_date="20260821",
        study_description=f"SYNTHETIC — QIDO {modality} study",
        modality=modality,
        series_count=1,
        instance_count=2,
        metadata_json={"synthetic": True},
    )
    session.add(study)
    session.flush()
    return study


def _override(engine, user: User):  # type: ignore[no-untyped-def]
    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user


def test_mwl_api_requires_auth_and_returns_contract_shape() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = {
            role: User(
                email=f"{role.value}@example.local",
                display_name=role.value,
                password_hash="not-used",
                role=role,
            )
            for role in (Role.PACS_ADMIN, Role.SCHEDULER)
        }
        session.add_all(users.values())
        seed_scheduled_case(session, accession="ACC-MWL-0100")
        session.commit()

    _override(engine, users[Role.PACS_ADMIN])
    try:
        client = TestClient(app)
        response = client.get("/api/v1/imaging/modality-worklist")
        assert response.status_code == 200
        payload = response.json()
        assert payload["resource_type"] == "modality_worklist"
        items = payload["items"]
        assert len(items) == 1
        item = items[0]
        assert item["accession_number"] == "ACC-MWL-0100"
        assert item["modality"] == "CT"
        assert item["external_patient_id"].startswith("SYN-")
        assert item["study_instance_uid"].startswith("0.0.0.0.mwl.")
        # Strict contract: unexpected fields absent.
        assert set(item) == {
            "accession_number",
            "external_patient_id",
            "patient_name",
            "patient_birth_date",
            "patient_sex",
            "modality",
            "requested_procedure_code",
            "requested_procedure_description",
            "study_instance_uid",
            "scheduled_start",
            "appointment_id",
            "order_id",
        }

        # Scheduler role is not authorized for PACS-side surfaces.
        app.dependency_overrides[get_current_user] = lambda: users[Role.SCHEDULER]
        assert client.get("/api/v1/imaging/modality-worklist").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_qido_study_query_filters_by_modality_patient_and_date() -> None:
    import_full_metadata()
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        users = {
            Role.PACS_ADMIN: User(
                email="pacs_admin@example.local",
                display_name="pacs_admin",
                password_hash="not-used",
                role=Role.PACS_ADMIN,
            )
        }
        session.add_all(users.values())
        seed_received_study(session, accession="ACC-QIDO-0001", modality="CT")
        seed_received_study(
            session,
            accession="ACC-QIDO-0002",
            modality="MR",
            patient_id="SYN-QIDO-0002",
        )
        session.commit()

    _override(engine, users[Role.PACS_ADMIN])
    try:
        client = TestClient(app)

        all_studies = client.get("/api/v1/imaging/dicom/studies")
        assert all_studies.status_code == 200
        rows = all_studies.json()
        assert len(rows) == 2
        row = rows[0]
        # DICOMweb QIDO-RS attribute names.
        assert {
            "0020000D",
            "00080050",
            "00100020",
            "00080060",
            "00200010",
        } <= set(row)
        assert row["0020000D"].startswith("1.2.826.0.1.3680043.10.9999.")

        ct_only = client.get("/api/v1/imaging/dicom/studies", params={"Modality": "CT"})
        assert [r["0020000D"] for r in ct_only.json()] == [rows[0]["0020000D"]] or len(
            ct_only.json()
        ) == 1

        by_patient = client.get(
            "/api/v1/imaging/dicom/studies", params={"PatientID": "SYN-QIDO-0002"}
        )
        assert len(by_patient.json()) == 1
        assert by_patient.json()[0]["00100020"] == "SYN-QIDO-0002"

        by_accession = client.get(
            "/api/v1/imaging/dicom/studies", params={"AccessionNumber": "ACC-QIDO-0001"}
        )
        assert len(by_accession.json()) == 1
        assert by_accession.json()[0]["00080050"] == "ACC-QIDO-0001"

        by_date = client.get("/api/v1/imaging/dicom/studies", params={"StudyDate": "20260821"})
        assert len(by_date.json()) == 2

        unknown_patient = client.get(
            "/api/v1/imaging/dicom/studies", params={"PatientID": "SYN-QIDO-NOPE"}
        )
        assert unknown_patient.json() == []
    finally:
        app.dependency_overrides.clear()
