"""Modality Worklist (DICOM MWL C-FIND equivalent) over scheduled imaging orders.

Read-only projection of booked, non-cancelled appointments in a queryable
window. This is the standards-shaped surface a real modality would query via
DICOM MWL C-FIND; here it is served deterministically from PostgreSQL.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.scheduling.models import (
    Appointment,
    AppointmentStatus,
    ImagingOrder,
    Referral,
    Slot,
    SyntheticPatient,
)

MAX_WINDOW_HOURS = 168
MAX_RESULTS = 100


@dataclass(frozen=True)
class WorklistEntry:
    """One scheduled procedure step as a modality would consume it."""

    accession_number: str
    external_patient_id: str
    patient_name: str
    patient_birth_date: str
    patient_sex: str | None
    modality: str
    requested_procedure_code: str
    requested_procedure_description: str
    study_instance_uid: str
    scheduled_start: datetime
    appointment_id: uuid.UUID
    order_id: uuid.UUID


def _stable_study_uid(order: ImagingOrder) -> str:
    """Deterministic placeholder UID; the real one arrives with the study."""
    return f"0.0.0.0.mwl.{order.accession_number.replace('-', '')}"


def list_modality_worklist(
    session: Session,
    *,
    modality: str | None = None,
    window_hours: int = 72,
    now: datetime | None = None,
) -> list[WorklistEntry]:
    """Return scheduled procedures ordered by start time.

    Only appointments that are booked or confirmed and not yet acquired are
    listed. Cancelled/rescheduled orders never appear. The look-ahead window
    is bounded to keep responses deterministic and small.
    """
    if not 1 <= window_hours <= MAX_WINDOW_HOURS:
        raise ValueError(f"window_hours must be between 1 and {MAX_WINDOW_HOURS}")
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    horizon = reference + timedelta(hours=window_hours)
    floor = reference - timedelta(hours=24)

    query = (
        select(Appointment, ImagingOrder, SyntheticPatient, Slot)
        .join(ImagingOrder, ImagingOrder.appointment_id == Appointment.id)
        .join(SyntheticPatient, SyntheticPatient.id == Appointment.patient_id)
        .outerjoin(Slot, Slot.id == Appointment.slot_id)
        .where(
            Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED]),
            ImagingOrder.status == "scheduled",
            ImagingOrder.scheduled_start >= floor,
            ImagingOrder.scheduled_start <= horizon,
        )
        .order_by(ImagingOrder.scheduled_start, ImagingOrder.accession_number)
        .limit(MAX_RESULTS)
    )
    if modality:
        normalized = modality.strip().upper()
        if normalized:
            query = query.where(ImagingOrder.modality == normalized)

    entries: list[WorklistEntry] = []
    for appointment, order, patient, _slot in session.execute(query):
        referral = session.get(Referral, appointment.referral_id)
        priority_suffix = ".stat" if referral is not None and referral.requested_priority else ""
        entries.append(
            WorklistEntry(
                accession_number=order.accession_number,
                external_patient_id=patient.external_patient_id,
                patient_name=f"{patient.last_name}^{patient.first_name}",
                patient_birth_date=patient.date_of_birth.strftime("%Y%m%d"),
                patient_sex=patient.sex_for_administrative_use,
                modality=order.modality,
                requested_procedure_code=order.requested_procedure_code,
                requested_procedure_description=order.requested_procedure_description,
                # Placeholder UID pattern: replaced by the actual study UID when
                # the acquired study reconciles against this accession.
                study_instance_uid=_stable_study_uid(order) + priority_suffix,
                scheduled_start=order.scheduled_start,
                appointment_id=appointment.id,
                order_id=order.id,
            )
        )
    return entries


def mark_order_acquired(session: Session, *, accession_number: str) -> bool:
    """Transition an order to acquired after its study has been received.

    Returns True when the transition applied; False when the order was already
    acquired (idempotent) ; raises for unknown accessions.
    """
    order = session.scalar(
        select(ImagingOrder).where(ImagingOrder.accession_number == accession_number)
    )
    if order is None:
        raise LookupError("order not found")
    if order.status == "acquired":
        return False
    order.status = "acquired"
    session.flush()
    return True
