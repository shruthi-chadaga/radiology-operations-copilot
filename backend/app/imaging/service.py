"""Deterministic Imaging Workspace projection and timeline services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.imaging.models import ImagingPriority, ImagingWorklistItem, ImagingWorklistStatus
from app.pacs.models import PacsStudy
from app.scheduling.models import (
    Appointment,
    AppointmentStatus,
    ImagingOrder,
    Referral,
    ReferralStatus,
    Slot,
    SyntheticPatient,
)


def _priority(value: str | None) -> ImagingPriority:
    normalized = (value or "").strip().lower()
    if normalized in {"stat", "emergency", "emergent"}:
        return ImagingPriority.STAT
    if normalized in {"urgent", "priority"}:
        return ImagingPriority.URGENT
    return ImagingPriority.ROUTINE


def _status(
    *,
    study: PacsStudy | None,
    appointment: Appointment | None,
    referral: Referral | None,
    order: ImagingOrder | None,
    existing: ImagingWorklistItem | None,
) -> ImagingWorklistStatus:
    if existing and existing.workflow_status in {
        ImagingWorklistStatus.IN_REVIEW,
        ImagingWorklistStatus.REPORT_DRAFT,
        ImagingWorklistStatus.CORRECTION_PENDING,
        ImagingWorklistStatus.FINALIZED,
    }:
        return existing.workflow_status
    if study is not None:
        return ImagingWorklistStatus.READY_FOR_REVIEW
    if appointment is not None and appointment.status == AppointmentStatus.CANCELLED:
        return ImagingWorklistStatus.CANCELLED
    if appointment is not None and appointment.status in {
        AppointmentStatus.BOOKED,
        AppointmentStatus.CONFIRMED,
    }:
        if order is not None and order.status == "acquired":
            return ImagingWorklistStatus.RECEIVED
        return ImagingWorklistStatus.SCHEDULED
    if referral is not None and referral.status in {
        ReferralStatus.READY,
        ReferralStatus.SCHEDULED,
    }:
        return ImagingWorklistStatus.SCHEDULED
    return ImagingWorklistStatus.SCHEDULED


def _find_item(
    session: Session,
    *,
    appointment_id: uuid.UUID | None,
    pacs_study_id: uuid.UUID | None,
    accession_number: str,
    pacs_patient_id: str,
) -> ImagingWorklistItem | None:
    if appointment_id is not None:
        item = session.scalar(
            select(ImagingWorklistItem).where(ImagingWorklistItem.appointment_id == appointment_id)
        )
        if item is not None:
            return item
    if pacs_study_id is not None:
        item = session.scalar(
            select(ImagingWorklistItem).where(ImagingWorklistItem.pacs_study_id == pacs_study_id)
        )
        if item is not None:
            return item
    # Accession is only a fallback when the synthetic PACS patient identifier
    # agrees. This prevents a malformed/colliding study from detaching a scheduled item.
    return session.scalar(
        select(ImagingWorklistItem).where(
            ImagingWorklistItem.accession_number == accession_number,
            ImagingWorklistItem.pacs_patient_id == pacs_patient_id,
            ImagingWorklistItem.pacs_study_id.is_(None),
        )
    )


def _upsert_study_item(
    session: Session,
    *,
    study: PacsStudy,
    patient_id: uuid.UUID | None = None,
    appointment: Appointment | None = None,
    referral: Referral | None = None,
    order: ImagingOrder | None = None,
    slot: Slot | None = None,
) -> ImagingWorklistItem:
    item = _find_item(
        session,
        appointment_id=appointment.id if appointment else None,
        pacs_study_id=study.id,
        accession_number=study.accession_number,
        pacs_patient_id=study.patient_id,
    )
    if item is None:
        item = ImagingWorklistItem(
            patient_id=patient_id,
            pacs_patient_id=study.patient_id,
            pacs_study_id=study.id,
            appointment_id=appointment.id if appointment else None,
            accession_number=study.accession_number,
            report_status="not_started",
        )
        session.add(item)
    item.patient_id = patient_id
    item.pacs_patient_id = study.patient_id
    item.pacs_study_id = study.id
    item.appointment_id = appointment.id if appointment else None
    item.accession_number = study.accession_number
    item.modality = study.modality if study else (order.modality if order else None)
    item.study_description = study.study_description
    item.priority = _priority(referral.requested_priority if referral else None)
    item.workflow_status = _status(
        study=study,
        appointment=appointment,
        referral=referral,
        order=order,
        existing=item,
    )
    item.scheduled_at = order.scheduled_start if order else (slot.start_time if slot else None)
    item.received_at = study.last_seen_at
    item.last_seen_at = study.last_seen_at
    item.updated_at = datetime.now(UTC)
    return item


def synchronize_worklist(session: Session) -> int:
    """Upsert all scheduled items and PACS observations without altering scheduler data."""
    changed = 0
    appointments = list(
        session.scalars(select(Appointment).order_by(Appointment.created_at, Appointment.id))
    )
    for appointment in appointments:
        referral = session.get(Referral, appointment.referral_id)
        order = session.scalar(
            select(ImagingOrder).where(ImagingOrder.appointment_id == appointment.id)
        )
        slot = session.get(Slot, appointment.slot_id)
        patient = session.get(SyntheticPatient, appointment.patient_id)
        matching_studies: list[PacsStudy] = []
        if patient is not None:
            matching_studies = list(
                session.scalars(
                    select(PacsStudy)
                    .where(
                        PacsStudy.accession_number == appointment.accession_number,
                        PacsStudy.patient_id == patient.external_patient_id,
                    )
                    .order_by(PacsStudy.last_seen_at.desc(), PacsStudy.id)
                )
            )
        study = matching_studies[0] if len(matching_studies) == 1 else None
        if study is not None:
            _upsert_study_item(
                session,
                study=study,
                patient_id=appointment.patient_id,
                appointment=appointment,
                referral=referral,
                order=order,
                slot=slot,
            )
        else:
            item = _find_item(
                session,
                appointment_id=appointment.id,
                pacs_study_id=None,
                accession_number=appointment.accession_number,
                pacs_patient_id=f"SCHEDULED-{appointment.accession_number}",
            )
            if item is None:
                item = ImagingWorklistItem(
                    patient_id=appointment.patient_id,
                    pacs_patient_id=f"SCHEDULED-{appointment.accession_number}",
                    appointment_id=appointment.id,
                    accession_number=appointment.accession_number,
                    modality=order.modality if order else None,
                    study_description=(order.requested_procedure_description if order else None),
                    report_status="not_started",
                )
                session.add(item)
            item.patient_id = appointment.patient_id
            item.pacs_patient_id = f"SCHEDULED-{appointment.accession_number}"
            item.appointment_id = appointment.id
            item.modality = order.modality if order else None
            item.study_description = order.requested_procedure_description if order else None
            item.priority = _priority(referral.requested_priority if referral else None)
            item.workflow_status = _status(
                study=None,
                appointment=appointment,
                referral=referral,
                order=order,
                existing=item,
            )
            item.scheduled_at = (
                order.scheduled_start if order else (slot.start_time if slot else None)
            )
            item.updated_at = datetime.now(UTC)
        changed += 1

    studies = list(
        session.scalars(select(PacsStudy).order_by(PacsStudy.last_seen_at, PacsStudy.id))
    )
    for study in studies:
        if session.scalar(
            select(ImagingWorklistItem).where(ImagingWorklistItem.pacs_study_id == study.id)
        ):
            continue
        _upsert_study_item(session, study=study)
        changed += 1
    session.flush()
    return changed


def build_timeline(session: Session, patient_id: uuid.UUID) -> list[dict[str, object]]:
    """Return stable, non-diagnostic referral, appointment, and study events."""
    events: list[dict[str, object]] = []
    referrals = list(
        session.scalars(
            select(Referral).where(Referral.patient_id == patient_id).order_by(Referral.received_at)
        )
    )
    for referral in referrals:
        events.append(
            {
                "event_type": "referral",
                "event_id": str(referral.id),
                "occurred_at": referral.received_at,
                "label": "Referral received",
                "detail": referral.requested_exam or "Imaging referral",
                "status": referral.status.value,
            }
        )
    appointments = list(
        session.scalars(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.created_at)
        )
    )
    for appointment in appointments:
        events.append(
            {
                "event_type": "appointment",
                "event_id": str(appointment.id),
                "occurred_at": appointment.created_at,
                "label": "Appointment scheduled",
                "detail": appointment.accession_number,
                "status": appointment.status.value,
            }
        )
    patient = session.get(SyntheticPatient, patient_id)
    if patient is not None:
        studies = list(
            session.scalars(
                select(PacsStudy)
                .where(PacsStudy.patient_id == patient.external_patient_id)
                .order_by(PacsStudy.last_seen_at)
            )
        )
        for study in studies:
            events.append(
                {
                    "event_type": "study",
                    "event_id": str(study.id),
                    "occurred_at": study.last_seen_at,
                    "label": "Study received",
                    "detail": study.accession_number,
                    "status": "ready_for_review",
                }
            )
    events.sort(
        key=lambda event: (event["occurred_at"], event["event_type"], event["event_id"]),
        reverse=True,
    )
    return events
