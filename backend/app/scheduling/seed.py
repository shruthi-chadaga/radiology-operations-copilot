"""Deterministic, conspicuously synthetic scheduling seed data."""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.scheduling.models import (
    ImagingService,
    Location,
    Referral,
    ReferralStatus,
    Schedule,
    Slot,
    SlotStatus,
    SyntheticPatient,
)

LOCATIONS = (
    ("central", "Central Synthetic Imaging"),
    ("north", "North Synthetic Imaging"),
    ("south", "South Synthetic Imaging"),
    ("east", "East Synthetic Imaging"),
    ("west", "West Synthetic Imaging"),
)
SERVICES = (
    ("CT-ABD", "CT abdomen", "CT", "abdomen", 30),
    ("CT-CHEST", "CT chest", "CT", "chest", 30),
    ("MR-HEAD", "MR head", "MR", "head", 45),
    ("MR-KNEE", "MR knee", "MR", "knee", 40),
    ("CR-CHEST", "CR chest", "CR", "chest", 15),
    ("US-ABD", "US abdomen", "US", "abdomen", 30),
    ("US-PELVIS", "US pelvis", "US", "pelvis", 30),
    ("NM-BONE", "NM bone", "NM", "bone", 60),
    ("CT-HEAD", "CT head", "CT", "head", 25),
    ("MR-SPINE", "MR spine", "MR", "spine", 50),
)


def seed_scheduling_demo(session: Session) -> None:
    if session.scalar(
        select(SyntheticPatient.id).where(SyntheticPatient.external_patient_id == "SYN-0001")
    ):
        return

    patients = [
        SyntheticPatient(
            external_patient_id=f"SYN-{index:04d}",
            first_name=f"Synthetic{index:02d}",
            last_name="Example",
            date_of_birth=date(1970 + index % 30, index % 12 + 1, index % 27 + 1),
            email=f"synthetic{index:02d}@example.local",
            preferred_contact_method="email",
            preferred_language="en",
            synthetic=True,
        )
        for index in range(1, 51)
    ]
    session.add_all(patients)
    locations = [
        Location(code=code, name=name, timezone="Europe/Berlin", active=True)
        for code, name in LOCATIONS
    ]
    session.add_all(locations)
    session.flush()

    services: list[ImagingService] = []
    for index, (code, name, modality, region, duration) in enumerate(SERVICES):
        service = ImagingService(
            code=code,
            name=name,
            modality=modality,
            body_region=region,
            default_duration_minutes=duration,
            location_id=locations[index % len(locations)].id,
            active=True,
        )
        services.append(service)
    session.add_all(services)
    session.flush()

    start_date = date(2026, 8, 1)
    for service_index, service in enumerate(services):
        schedule = Schedule(
            imaging_service_id=service.id,
            location_id=service.location_id,
            start_date=start_date,
            end_date=start_date + timedelta(days=29),
            status="active",
        )
        session.add(schedule)
        session.flush()
        for day_offset in range(30):
            start = datetime.combine(
                start_date + timedelta(days=day_offset),
                time(hour=8 + service_index % 8),
                tzinfo=UTC,
            )
            session.add(
                Slot(
                    schedule_id=schedule.id,
                    start_time=start,
                    end_time=start + timedelta(minutes=service.default_duration_minutes),
                    status=SlotStatus.FREE,
                    capacity=1,
                    version=1,
                )
            )

    for index in range(40):
        service = services[index % len(services)]
        location = locations[index % len(locations)]
        authorized = index % 5 != 0
        auth_text = "Authorization approved." if authorized else "Authorization not supplied."
        session.add(
            Referral(
                referral_number=f"REF-SEED-{index + 1:04d}",
                patient_id=patients[index].id,
                source_text=(
                    f"Routine {service.modality} {service.body_region} requested at "
                    f"{location.name}. {auth_text}"
                ),
                requested_exam=service.name,
                modality=service.modality,
                body_region=service.body_region,
                requested_priority="routine",
                preferred_location=location.name,
                authorization_status="approved" if authorized else None,
                status=ReferralStatus.NEW,
                completeness_status="not_reviewed",
                extraction_confidence=None,
            )
        )
    session.flush()
