"""Scheduling persistence model for synthetic referrals and transactional booking."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReferralStatus(StrEnum):
    NEW = "new"
    REVIEW = "review"
    READY = "ready"
    EXCEPTION = "exception"
    SCHEDULED = "scheduled"


class SlotStatus(StrEnum):
    FREE = "free"
    HELD = "held"
    BUSY = "busy"
    BLOCKED = "blocked"


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class SyntheticPatient(Base):
    __tablename__ = "synthetic_patients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    external_patient_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex_for_administrative_use: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str] = mapped_column(String(320))
    preferred_contact_method: Mapped[str] = mapped_column(String(32), default="email")
    preferred_language: Mapped[str] = mapped_column(String(16), default="en")
    accessibility_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    referral_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("synthetic_patients.id"), index=True)
    source_text: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), default="text")
    requested_exam: Mapped[str | None] = mapped_column(String(200), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    body_region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    laterality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_for_exam: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    referring_provider: Mapped[str | None] = mapped_column(String(160), nullable=True)
    preferred_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    earliest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contrast_indicator: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sedation_indicator: Mapped[str | None] = mapped_column(String(32), nullable=True)
    authorization_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus, native_enum=False, length=32), default=ReferralStatus.NEW, index=True
    )
    completeness_status: Mapped[str] = mapped_column(String(32), default="not_reviewed")
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReferralFieldExtraction(Base):
    __tablename__ = "referral_field_extractions"
    __table_args__ = (
        UniqueConstraint("referral_id", "field_name", name="uq_referral_current_field"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    referral_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("referrals.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    extracted_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(64))
    corrected_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    address_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ImagingService(Base):
    __tablename__ = "imaging_services"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    modality: Mapped[str] = mapped_column(String(16), index=True)
    body_region: Mapped[str] = mapped_column(String(80))
    default_duration_minutes: Mapped[int] = mapped_column(Integer)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    imaging_service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imaging_services.id"))
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locations.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="active")


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedules.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus, native_enum=False, length=16), default=SlotStatus.FREE, index=True
    )
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index(
            "uq_appointment_active_referral",
            "referral_id",
            unique=True,
            postgresql_where=text("status IN ('BOOKED', 'CONFIRMED')"),
            sqlite_where=text("status IN ('BOOKED', 'CONFIRMED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    accession_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("synthetic_patients.id"), index=True)
    referral_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("referrals.id"), index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("slots.id"), index=True)
    imaging_service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imaging_services.id"))
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, length=24),
        default=AppointmentStatus.BOOKED,
        index=True,
    )
    booked_by_type: Mapped[str] = mapped_column(String(32))
    booking_reason: Mapped[str] = mapped_column(Text)
    preparation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImagingOrder(Base):
    __tablename__ = "imaging_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    accession_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("synthetic_patients.id"))
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"), unique=True)
    requested_procedure_code: Mapped[str] = mapped_column(String(40))
    requested_procedure_description: Mapped[str] = mapped_column(String(200))
    modality: Mapped[str] = mapped_column(String(16))
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="scheduled")


class AppointmentHistory(Base):
    __tablename__ = "appointment_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("appointments.id"), index=True)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
