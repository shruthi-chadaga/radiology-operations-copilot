from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.audit.models import AuditEvent
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.scheduling.models import (
    ImagingOrder,
    ImagingService,
    Location,
    ReferralFieldExtraction,
    Schedule,
    Slot,
    SlotStatus,
    SyntheticPatient,
)


def test_scheduling_api_connects_referral_extraction_validation_ranking_and_booking() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    scheduler = User(
        email="scheduler@example.local",
        display_name="Synthetic Scheduler",
        password_hash="unused-test-hash",
        role=Role.SCHEDULER,
    )
    with Session(engine) as session:
        patient = SyntheticPatient(
            external_patient_id="SYN-API-001",
            first_name="Nova",
            last_name="Example",
            date_of_birth=date(1988, 5, 4),
            email="nova@example.local",
        )
        location = Location(
            code="central", name="Central Imaging", timezone="Europe/Berlin", active=True
        )
        session.add_all([scheduler, patient, location])
        session.flush()
        service = ImagingService(
            code="CT-ABD",
            name="CT abdomen",
            modality="CT",
            body_region="abdomen",
            default_duration_minutes=30,
            location_id=location.id,
            active=True,
        )
        session.add(service)
        session.flush()
        schedule = Schedule(
            imaging_service_id=service.id,
            location_id=location.id,
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 30),
            status="active",
        )
        session.add(schedule)
        session.flush()
        for index, hour in enumerate((9, 11, 14), start=1):
            start = datetime(2026, 8, index + 3, hour, tzinfo=UTC)
            session.add(
                Slot(
                    schedule_id=schedule.id,
                    start_time=start,
                    end_time=start + timedelta(minutes=30),
                    status=SlotStatus.FREE,
                    capacity=1,
                    version=1,
                )
            )
        session.commit()
        patient_id = str(patient.id)
        service_id = str(service.id)
        session.refresh(scheduler)

    def override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: scheduler
    client = TestClient(app)
    try:
        missing_attestation = client.post(
            "/api/v1/referrals",
            json={
                "patient_id": patient_id,
                "source_text": "[SYNTHETIC] Routine CT abdomen requested.",
            },
        )
        assert missing_attestation.status_code == 422
        unmarked = client.post(
            "/api/v1/referrals",
            json={
                "patient_id": patient_id,
                "source_text": "Routine CT abdomen requested.",
                "synthetic_data_confirmed": True,
            },
        )
        assert unmarked.status_code == 422
        created = client.post(
            "/api/v1/referrals",
            json={
                "patient_id": patient_id,
                "source_text": (
                    "[SYNTHETIC] Routine CT abdomen requested at Central Imaging. "
                    "Authorization approved."
                ),
                "synthetic_data_confirmed": True,
            },
            headers={"X-Request-ID": "req-ref-create"},
        )
        assert created.status_code == 201
        referral_id = created.json()["id"]
        assert created.json()["source_text"].startswith("[SYNTHETIC] Routine CT abdomen")

        queue = client.get("/api/v1/referrals")
        assert queue.status_code == 200
        assert queue.json()["items"][0]["id"] == referral_id

        extracted = client.post(f"/api/v1/referrals/{referral_id}/extract")
        assert extracted.status_code == 200
        assert extracted.json()["modality"]["value"] == "CT"
        assert extracted.json()["model_name"] == "mock-v1"
        repeated_extraction = client.post(f"/api/v1/referrals/{referral_id}/extract")
        assert repeated_extraction.status_code == 200
        with Session(engine) as session:
            extraction_count = session.scalar(
                select(func.count())
                .select_from(ReferralFieldExtraction)
                .where(ReferralFieldExtraction.referral_id == UUID(referral_id))
            )
            assert extraction_count == 9

        validated = client.post(f"/api/v1/referrals/{referral_id}/validate")
        assert validated.status_code == 200
        assert validated.json()["is_complete"] is True
        assert validated.json()["issues"] == []

        recommended = client.post(
            f"/api/v1/referrals/{referral_id}/slot-recommendations",
            json={"preferred_location_code": "central", "preferred_time_of_day": "morning"},
        )
        assert recommended.status_code == 200
        assert len(recommended.json()["items"]) == 3
        first = recommended.json()["items"][0]
        assert "requested date range" in first["explanation"]

        booked = client.post(
            "/api/v1/appointments",
            json={
                "referral_id": referral_id,
                "slot_id": first["slot_id"],
                "imaging_service_id": service_id,
                "expected_slot_version": 1,
                "booking_reason": "User accepted highest-ranked deterministic slot",
            },
            headers={"X-Request-ID": "req-api-book", "X-Correlation-ID": "corr-api-book"},
        )
        assert booked.status_code == 201
        assert booked.json()["accession_number"].startswith("ACC-")
        denied_booking = client.post(
            "/api/v1/appointments",
            json={
                "referral_id": referral_id,
                "slot_id": first["slot_id"],
                "imaging_service_id": service_id,
                "expected_slot_version": 1,
                "booking_reason": "Rejected duplicate synthetic booking",
            },
        )
        assert denied_booking.status_code == 409

        rescheduled = client.post(
            f"/api/v1/appointments/{booked.json()['id']}/reschedule",
            json={
                "new_slot_id": recommended.json()["items"][1]["slot_id"],
                "expected_new_slot_version": 1,
                "reason": "Synthetic patient accepted another ranked slot",
            },
        )
        assert rescheduled.status_code == 200
        assert rescheduled.json()["id"] != booked.json()["id"]

        cancelled = client.post(
            f"/api/v1/appointments/{rescheduled.json()['id']}/cancel",
            json={"reason": "Synthetic patient requested cancellation"},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        denied_cancellation = client.post(
            f"/api/v1/appointments/{rescheduled.json()['id']}/cancel",
            json={"reason": "Rejected duplicate synthetic cancellation"},
        )
        assert denied_cancellation.status_code == 409

        with Session(engine) as session:
            order = session.scalar(
                select(ImagingOrder).where(
                    ImagingOrder.accession_number == booked.json()["accession_number"]
                )
            )
            assert order is not None
            audit_actions = set(session.scalars(select(AuditEvent.action)))
            assert "scheduling.slot_recommendations.generated" in audit_actions
            assert "scheduling.appointment.booking_denied" in audit_actions
            assert "scheduling.appointment.cancellation_denied" in audit_actions
    finally:
        app.dependency_overrides.clear()
