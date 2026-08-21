"""Imaging Workspace APIs: worklist, patient context, viewer, and reports."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.session import get_db
from app.imaging.delivery import ShareDeliveryError, rotate_and_send_share_link
from app.imaging.models import (
    ImagingPriority,
    ImagingWorklistItem,
    RadiologyReport,
    RadiologyReportShare,
    RadiologyReportShareStatus,
    RadiologyReportVersion,
    ReportStatus,
)
from app.imaging.mpps import (
    ProcedureStepError,
    complete_step,
    discontinue_step,
    list_steps,
    start_step,
)
from app.imaging.print_export import PrintExportError, export_report_pdf
from app.imaging.reporting import (
    ReportWorkflowError,
    create_correction,
    finalize_report,
    get_report,
    save_draft,
)
from app.imaging.schemas import (
    ImagingWorklistItemResponse,
    ImagingWorklistPage,
    PatientTimelineEvent,
    PatientTimelineResponse,
    ReportCorrectionRequest,
    ReportDraftRequest,
    ReportFinalizeRequest,
    ReportResponse,
    ReportVersionResponse,
    ShareCreatedResponse,
    ShareCreateRequest,
    SharedReportResponse,
    ShareEmailRequest,
    SharePage,
    ShareResolveRequest,
    ShareResponse,
    ViewerComparisonResponse,
    ViewerStudyResponse,
)
from app.imaging.service import build_timeline, synchronize_worklist
from app.imaging.sharing import (
    ShareWorkflowError,
    create_share,
    list_shares,
    resolve_active_share,
    revoke_share,
    shared_report_payload,
)
from app.imaging.viewer import find_prior_studies, first_instance_id, is_synthetic_study
from app.imaging.worklist_service import list_modality_worklist
from app.pacs.adapter import PacsAdapter
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.models import MockEhrDelivery, PacsNode, PacsStudy
from app.scheduling.models import SyntheticPatient

router = APIRouter(prefix="/imaging", tags=["imaging-workspace"])
_READ_ROLES = {Role.PACS_ADMIN, Role.OPERATIONS_MANAGER, Role.AUDITOR}
_WRITE_ROLES = {Role.PACS_ADMIN, Role.OPERATIONS_MANAGER}
_REPORT_ROLES = {Role.PACS_ADMIN, Role.OPERATIONS_MANAGER}


def _authorize(user: User, *, write: bool = False) -> None:
    allowed = _WRITE_ROLES if write else _READ_ROLES
    if user.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _authorize_reporter(user: User) -> None:
    if user.role not in _REPORT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Report authoring requires an imaging operator role",
        )


def _item_response(session: Session, item: ImagingWorklistItem) -> ImagingWorklistItemResponse:
    patient = session.get(SyntheticPatient, item.patient_id) if item.patient_id else None
    study_date: str | None = None
    if item.pacs_study_id:
        study = session.get(PacsStudy, item.pacs_study_id)
        study_date = study.study_date if study else None
    return ImagingWorklistItemResponse(
        id=str(item.id),
        patient_id=str(item.patient_id) if item.patient_id else None,
        pacs_patient_id=item.pacs_patient_id,
        patient_name=(f"{patient.first_name} {patient.last_name}" if patient else None),
        patient_birth_date=patient.date_of_birth.isoformat() if patient else None,
        accession_number=item.accession_number,
        modality=item.modality,
        study_description=item.study_description,
        study_date=study_date,
        workflow_status=item.workflow_status.value,
        priority=item.priority.value,
        assigned_reader_id=item.assigned_reader_id,
        report_status=item.report_status,
        scheduled_at=item.scheduled_at,
        received_at=item.received_at,
        pacs_study_id=str(item.pacs_study_id) if item.pacs_study_id else None,
        appointment_id=str(item.appointment_id) if item.appointment_id else None,
    )


def _worklist_response(db: Session) -> ImagingWorklistPage:
    priority_rank = case(
        (ImagingWorklistItem.priority == ImagingPriority.STAT, 3),
        (ImagingWorklistItem.priority == ImagingPriority.URGENT, 2),
        else_=1,
    )
    items = db.scalars(
        select(ImagingWorklistItem).order_by(
            priority_rank.desc(),
            ImagingWorklistItem.received_at.desc().nullslast(),
            ImagingWorklistItem.scheduled_at,
            ImagingWorklistItem.accession_number,
        )
    )
    return ImagingWorklistPage(
        items=[_item_response(db, item) for item in items],
        generated_at=datetime.now(UTC),
    )


def _viewer_study(
    study: PacsStudy, *, representative_instance_id: str | None
) -> ViewerStudyResponse:
    return ViewerStudyResponse(
        study_id=str(study.id),
        accession_number=study.accession_number,
        study_instance_uid=study.study_instance_uid,
        study_date=study.study_date,
        modality=study.modality,
        study_description=study.study_description,
        is_synthetic=is_synthetic_study(study),
        preview_available=representative_instance_id is not None,
        representative_instance_id=representative_instance_id,
        series_count=study.series_count,
        instance_count=study.instance_count,
    )


def _adapter_for(study: PacsStudy, adapters: dict[str, PacsAdapter], db: Session) -> PacsAdapter:
    node = db.get(PacsNode, study.node_id)
    if node is None or node.adapter_key not in adapters:
        raise HTTPException(status_code=503, detail="PACS adapter unavailable")
    return adapters[node.adapter_key]


def _instance_belongs_to_study(adapter: PacsAdapter, study: PacsStudy, instance_id: str) -> bool:
    for series in adapter.list_series(study.orthanc_study_id):
        instances = series.get("instances")
        if not isinstance(instances, list):
            continue
        if any(
            isinstance(instance, dict) and instance.get("orthanc_instance_id") == instance_id
            for instance in instances
        ):
            return True
    return False


def _report_version_response(version: RadiologyReportVersion) -> ReportVersionResponse:
    return ReportVersionResponse(
        id=str(version.id),
        version_number=version.version_number,
        kind=version.kind.value,
        author_id=version.author_id,
        indication=version.indication,
        findings=version.findings,
        impression=version.impression,
        correction_reason=version.correction_reason,
        created_at=version.created_at,
    )


def _report_response(db: Session, report: RadiologyReport) -> ReportResponse:
    versions = list(
        db.scalars(
            select(RadiologyReportVersion)
            .where(RadiologyReportVersion.report_id == report.id)
            .order_by(RadiologyReportVersion.version_number)
        )
    )
    return ReportResponse(
        id=str(report.id),
        study_id=str(report.study_id),
        status=report.status.value,
        current_version_number=report.current_version_number,
        finalized_by=report.finalized_by,
        finalized_at=report.finalized_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
        versions=[_report_version_response(version) for version in versions],
    )


def _audit_report(
    db: Session,
    user: User,
    *,
    action: str,
    report: RadiologyReport,
    reason: str,
) -> None:
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action=action,
        entity_type="radiology_report",
        entity_id=str(report.id),
        decision_reason=reason,
        correlation_id=f"report-{report.id}",
        request_id=f"report-{report.id}",
        success=True,
        after_state={
            "study_id": str(report.study_id),
            "status": report.status.value,
            "version": report.current_version_number,
        },
    )


@router.get("/worklist", response_model=ImagingWorklistPage)
def get_worklist(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ImagingWorklistPage:
    _authorize(user)
    return _worklist_response(db)


@router.post("/worklist/synchronize", response_model=ImagingWorklistPage)
def synchronize_worklist_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ImagingWorklistPage:
    _authorize(user, write=True)
    synchronize_worklist(db)
    db.commit()
    return _worklist_response(db)


@router.get("/patients/{patient_id}/timeline", response_model=PatientTimelineResponse)
def get_patient_timeline(
    patient_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PatientTimelineResponse:
    _authorize(user)
    patient = db.get(SyntheticPatient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Synthetic patient not found")
    return PatientTimelineResponse(
        patient_id=str(patient.id),
        external_patient_id=patient.external_patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        events=[PatientTimelineEvent(**event) for event in build_timeline(db, patient.id)],
    )


@router.get("/studies/{study_id}/viewer", response_model=ViewerComparisonResponse)
def get_viewer_context(
    study_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> ViewerComparisonResponse:
    _authorize(user)
    study = db.get(PacsStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="PACS study metadata not found")
    if not is_synthetic_study(study):
        raise HTTPException(status_code=409, detail="Only attested synthetic studies can be viewed")
    adapter = _adapter_for(study, adapters, db)
    try:
        representative = first_instance_id(adapter.list_series(study.orthanc_study_id))
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Could not prepare synthetic viewer context"
        ) from exc
    priors: list[ViewerStudyResponse] = []
    for prior in find_prior_studies(db, study):
        try:
            prior_adapter = _adapter_for(prior, adapters, db)
            prior_instance = first_instance_id(prior_adapter.list_series(prior.orthanc_study_id))
        except Exception:
            prior_instance = None
        priors.append(_viewer_study(prior, representative_instance_id=prior_instance))
    return ViewerComparisonResponse(
        current=_viewer_study(study, representative_instance_id=representative),
        priors=priors,
    )


@router.get("/studies/{study_id}/preview/{instance_id}")
def get_viewer_preview(
    study_id: uuid.UUID,
    instance_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> Response:
    _authorize(user)
    study = db.get(PacsStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="PACS study metadata not found")
    if not is_synthetic_study(study):
        raise HTTPException(
            status_code=409,
            detail="Only attested synthetic studies can be previewed",
        )
    adapter = _adapter_for(study, adapters, db)
    try:
        if not _instance_belongs_to_study(adapter, study, instance_id):
            raise HTTPException(status_code=404, detail="Preview instance not found in study")
        content, media_type = adapter.render_instance_preview(instance_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not render synthetic preview") from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Synthetic-Preview": "true"},
    )


@router.get("/studies/{study_id}/report", response_model=ReportResponse)
def get_study_report(
    study_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportResponse:
    _authorize(user)
    study = db.get(PacsStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="PACS study metadata not found")
    if not is_synthetic_study(study):
        raise HTTPException(
            status_code=409,
            detail="Only attested synthetic studies can be reported",
        )
    report = get_report(db, study_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not started")
    return _report_response(db, report)


@router.post("/studies/{study_id}/report/draft", response_model=ReportResponse)
def save_study_report_draft(
    study_id: uuid.UUID,
    payload: ReportDraftRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportResponse:
    _authorize_reporter(user)
    try:
        report, _ = save_draft(
            db,
            study_id=study_id,
            author_id=str(user.id),
            **payload.model_dump(),
        )
    except ReportWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    _audit_report(
        db,
        user,
        action="imaging.report.draft_saved",
        report=report,
        reason="User authored synthetic draft",
    )
    db.commit()
    db.refresh(report)
    return _report_response(db, report)


@router.post("/reports/{report_id}/finalize", response_model=ReportResponse)
def finalize_study_report(
    report_id: uuid.UUID,
    payload: ReportFinalizeRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportResponse:
    _authorize_reporter(user)
    try:
        report, _ = finalize_report(
            db,
            report_id=report_id,
            author_id=str(user.id),
            **payload.model_dump(),
        )
    except ReportWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    _audit_report(
        db,
        user,
        action="imaging.report.finalized",
        report=report,
        reason="User finalized authored report",
    )
    db.commit()
    db.refresh(report)
    return _report_response(db, report)


@router.post("/reports/{report_id}/correction", response_model=ReportResponse)
def correct_study_report(
    report_id: uuid.UUID,
    payload: ReportCorrectionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportResponse:
    _authorize_reporter(user)
    try:
        report, _ = create_correction(
            db,
            report_id=report_id,
            author_id=str(user.id),
            **payload.model_dump(),
        )
    except ReportWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    _audit_report(
        db,
        user,
        action="imaging.report.correction_created",
        report=report,
        reason="User created a new immutable correction version",
    )
    db.commit()
    db.refresh(report)
    return _report_response(db, report)


def _share_response(share: RadiologyReportShare) -> ShareResponse:
    status_value = (
        share.status
        if isinstance(share.status, RadiologyReportShareStatus)
        else RadiologyReportShareStatus(share.status)
    )
    return ShareResponse(
        id=str(share.id),
        report_id=str(share.report_id),
        study_id=str(share.study_id),
        recipient_label=share.recipient_label,
        status=status_value.value,
        created_by=share.created_by,
        created_at=share.created_at,
        expires_at=share.expires_at,
        revoked_at=share.revoked_at,
    )


def _audit_share(
    db: Session,
    user: User,
    *,
    action: str,
    share: RadiologyReportShare,
    reason: str,
    extra_state: dict[str, str] | None = None,
) -> None:
    status_value = (
        share.status
        if isinstance(share.status, RadiologyReportShareStatus)
        else RadiologyReportShareStatus(share.status)
    )
    expires_at = (
        share.expires_at.isoformat()
        if hasattr(share.expires_at, "isoformat")
        else str(share.expires_at)
    )
    after_state = {
        "report_id": str(share.report_id),
        "recipient_label": share.recipient_label,
        "status": status_value.value,
        "expires_at": expires_at,
        "raw_token_stored": False,
    }
    if extra_state:
        after_state.update(extra_state)
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action=action,
        entity_type="radiology_report_share",
        entity_id=str(share.id),
        decision_reason=reason,
        correlation_id=f"share-{share.id}",
        request_id=f"share-{share.id}",
        success=True,
        after_state=after_state,
    )


@router.post(
    "/reports/{report_id}/shares",
    response_model=ShareCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_report_share(
    report_id: uuid.UUID,
    payload: ShareCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ShareCreatedResponse:
    _authorize_reporter(user)
    try:
        share, raw_token = create_share(
            db,
            report_id=report_id,
            created_by=str(user.id),
            recipient_label=payload.recipient_label,
            expires_in_hours=payload.expires_in_hours,
        )
    except ShareWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    _audit_share(
        db,
        user,
        action="imaging.share.created",
        share=share,
        reason="User allowlisted a recipient for the finalized report",
    )
    db.commit()
    db.refresh(share)
    response = ShareCreatedResponse(
        **_share_response(share).model_dump(),
        token=raw_token,
    )
    return response


@router.get("/reports/{report_id}/shares", response_model=SharePage)
def list_report_shares(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SharePage:
    _authorize(user)
    shares = list_shares(db, report_id=report_id)
    return SharePage(items=[_share_response(share) for share in shares])


@router.delete("/reports/shares/{share_id}", response_model=ShareResponse)
def revoke_report_share(
    share_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ShareResponse:
    _authorize(user, write=True)
    try:
        share = revoke_share(db, share_id=share_id, revoked_by=str(user.id))
    except ShareWorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    _audit_share(
        db,
        user,
        action="imaging.share.revoked",
        share=share,
        reason="User revoked the share allowlist entry",
    )
    db.commit()
    db.refresh(share)
    return _share_response(share)


@router.post("/shares/resolve", response_model=SharedReportResponse)
def resolve_shared_report(
    payload: ShareResolveRequest,
    db: Annotated[Session, Depends(get_db)],
) -> SharedReportResponse:
    """Token-authenticated recipient view; the token itself is the credential.

    Invalid, expired, and revoked tokens return an identical 403 so callers
    cannot distinguish between them.
    """
    share = resolve_active_share(db, raw_token=payload.token)
    if share is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Share link is not valid",
        )
    bounded = shared_report_payload(db, share)
    return SharedReportResponse(**bounded)


@router.get("/procedure-steps")
def list_procedure_steps(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """MPPS-lite lifecycle history; read-only evidence of modality activity."""
    _authorize(user)
    return {"resource_type": "procedure_steps", "items": list_steps(db)}


@router.post("/procedure-steps/{accession_number}/start")
def start_procedure_step(
    accession_number: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _authorize(user, write=True)
    try:
        step = start_step(db, accession_number=accession_number, started_by=str(user.id))
    except ProcedureStepError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    db.commit()
    return step


class StepCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    performed_series_count: int = Field(ge=1, le=1000)


@router.post("/procedure-steps/{step_id}/complete")
def complete_procedure_step(
    step_id: uuid.UUID,
    payload: StepCompleteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _authorize(user, write=True)
    try:
        step = complete_step(
            db,
            step_id=step_id,
            performed_series_count=payload.performed_series_count,
            completed_by=str(user.id),
        )
    except ProcedureStepError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    db.commit()
    return step


class StepDiscontinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=300)


@router.post("/procedure-steps/{step_id}/discontinue")
def discontinue_procedure_step(
    step_id: uuid.UUID,
    payload: StepDiscontinueRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    _authorize(user, write=True)
    try:
        step = discontinue_step(
            db,
            step_id=step_id,
            reason=payload.reason,
            discontinued_by=str(user.id),
        )
    except ProcedureStepError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    db.commit()
    return step


@router.post("/mock-ehr/receive", status_code=status.HTTP_201_CREATED)
def mock_ehr_receive(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Deliver a finalized report to the local mock EHR (no external calls).

    Stores delivery evidence only; the FHIR resource is generated on demand
    and never persisted here. One delivery per report.
    """
    _authorize(user, write=True)
    report = db.get(RadiologyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != ReportStatus.FINALIZED:
        raise HTTPException(
            status_code=409,
            detail="Only a finalized report can be delivered",
        )
    existing = db.scalar(select(MockEhrDelivery).where(MockEhrDelivery.report_id == report.id))
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This report has already been delivered to the mock EHR",
        )
    if report.current_version_number is None:
        raise HTTPException(status_code=409, detail="Report has no version to deliver")
    delivery = MockEhrDelivery(
        report_id=report.id,
        study_id=report.study_id,
        receiver="mock-ehr",
        resource_type="DiagnosticReport",
        status="received",
        version_number=report.current_version_number,
        received_by=str(user.id),
    )
    db.add(delivery)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="This report has already been delivered to the mock EHR",
        ) from exc
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="imaging.mock_ehr.received",
        entity_type="mock_ehr_delivery",
        entity_id=str(delivery.id),
        decision_reason=(
            "Finalized report handed to the local mock EHR receiver "
            "(demonstration only; no external system contacted)"
        ),
        correlation_id=f"report-{report.id}",
        request_id=f"report-{report.id}",
        success=True,
        after_state={
            "report_id": str(report.id),
            "version": report.current_version_number,
            "receiver": "mock-ehr",
            "external": False,
        },
    )
    db.commit()
    return {
        "id": str(delivery.id),
        "accepted": True,
        "receiver": "mock-ehr",
        "resource_type": "DiagnosticReport",
        "report_id": str(report.id),
        "version_number": delivery.version_number,
        "received_at": delivery.received_at.isoformat(),
    }


@router.get("/mock-ehr/inbox")
def mock_ehr_inbox(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Bounded listing of mock-EHR deliveries; no report content is exposed."""
    _authorize(user)
    deliveries = list(
        db.scalars(
            select(MockEhrDelivery)
            .order_by(MockEhrDelivery.received_at.desc(), MockEhrDelivery.id)
            .limit(200)
        )
    )
    return {
        "resource_type": "mock_ehr_inbox",
        "items": [
            {
                "id": str(delivery.id),
                "report_id": str(delivery.report_id),
                "study_id": str(delivery.study_id),
                "receiver": delivery.receiver,
                "resource_type": delivery.resource_type,
                "status": delivery.status,
                "version_number": delivery.version_number,
                "received_by": delivery.received_by,
                "received_at": delivery.received_at.isoformat(),
            }
            for delivery in deliveries
        ],
    }


@router.post("/reports/shares/{share_id}/email", response_model=ShareResponse)
def email_report_share(
    share_id: uuid.UUID,
    payload: ShareEmailRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ShareResponse:
    """Email a fresh share link; rotating the token invalidates the old one."""
    _authorize(user, write=True)
    share = db.scalar(
        select(RadiologyReportShare)
        .where(RadiologyReportShare.id == share_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    try:
        rotate_and_send_share_link(db, share=share, recipient_email=payload.recipient_email)
    except ShareDeliveryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    _audit_share(
        db,
        user,
        action="imaging.share.emailed",
        share=share,
        reason="Share link emailed; previous token rotated and invalidated",
        extra_state={"recipient_email_domain": payload.recipient_email.split("@")[-1]},
    )
    db.commit()
    db.refresh(share)
    return _share_response(share)


def _fhir_diagnostic_report(db: Session, report: RadiologyReport) -> dict[str, object]:
    """Build a mock FHIR DiagnosticReport from the finalized authored report."""
    study = db.get(PacsStudy, report.study_id)
    versions = list(
        db.scalars(
            select(RadiologyReportVersion)
            .where(RadiologyReportVersion.report_id == report.id)
            .order_by(RadiologyReportVersion.version_number)
        )
    )
    current = next(
        (
            version
            for version in reversed(versions)
            if version.version_number == report.current_version_number
        ),
        None,
    )
    return {
        "resourceType": "DiagnosticReport",
        "id": str(report.id),
        "meta": {
            "tag": [
                {"system": "radiology-operations-copilot", "code": "synthetic"},
                {
                    "system": "radiology-operations-copilot",
                    "code": "mock-export",
                },
            ]
        },
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "18748-4",
                    "display": "Diagnostic imaging study",
                }
            ]
        },
        "subject": {"reference": f"Patient/{study.patient_id if study else 'unknown'}"},
        "effectiveDateTime": report.finalized_at.isoformat() if report.finalized_at else None,
        "issued": report.updated_at.isoformat(),
        "performer": [{"display": f"Synthetic author {report.finalized_by or 'unknown'}"}],
        "conclusion": current.impression if current else "",
        "presentedForm": [
            {
                "contentType": "text/plain",
                "data": current.findings if current else "",
            }
        ],
    }


@router.get("/reports/{report_id}/fhir")
def export_report_fhir(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Mock FHIR DiagnosticReport export; synthetic-only, no external calls."""
    _authorize(user)
    report = db.get(RadiologyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != ReportStatus.FINALIZED:
        raise HTTPException(
            status_code=409,
            detail="Only a finalized report can be exported",
        )
    append_audit_event(
        db,
        actor=AuditActor("user", str(user.id)),
        action="imaging.report.fhir_exported",
        entity_type="radiology_report",
        entity_id=str(report.id),
        decision_reason="Mock FHIR DiagnosticReport exported for demonstration",
        correlation_id=f"report-{report.id}",
        request_id=f"report-{report.id}",
        success=True,
        after_state={
            "status": report.status.value,
            "version": report.current_version_number,
            "mock": True,
        },
    )
    db.commit()
    return _fhir_diagnostic_report(db, report)


@router.get("/reports/{report_id}/print")
def export_report_print(
    report_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Print/PDF export of a finalized report; synthetic watermark included."""
    _authorize(user)
    try:
        content, _report = export_report_pdf(db, report_id=report_id, exported_by=str(user.id))
    except PrintExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    db.commit()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (f'inline; filename="synthetic-report-{report_id}.pdf"'),
            "Cache-Control": "no-store",
        },
    )


@router.get("/modality-worklist")
def get_modality_worklist(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    modality: str | None = None,
    window_hours: int = 72,
) -> dict[str, object]:
    """DICOM MWL C-FIND equivalent over scheduled, not-yet-acquired orders."""
    _authorize(user, write=True)
    try:
        entries = list_modality_worklist(db, modality=modality, window_hours=window_hours)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "resource_type": "modality_worklist",
        "items": [
            {
                "accession_number": entry.accession_number,
                "external_patient_id": entry.external_patient_id,
                "patient_name": entry.patient_name,
                "patient_birth_date": entry.patient_birth_date,
                "patient_sex": entry.patient_sex,
                "modality": entry.modality,
                "requested_procedure_code": entry.requested_procedure_code,
                "requested_procedure_description": entry.requested_procedure_description,
                "study_instance_uid": entry.study_instance_uid,
                "scheduled_start": entry.scheduled_start.isoformat(),
                "appointment_id": str(entry.appointment_id),
                "order_id": str(entry.order_id),
            }
            for entry in entries
        ],
    }


_QIDO_TAG_BY_FIELD = {
    "study_instance_uid": "0020000D",
    "accession_number": "00080050",
    "patient_id": "00100020",
    "modality": "00080060",
    "study_date": "00080020",
    "study_description": "00081030",
    "patient_name": "00100010",
    "series_count": "00201206",
    "instance_count": "00201208",
}


@router.get("/dicom/studies")
def query_studies_dicomweb_style(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    Modality: str | None = None,
    PatientID: str | None = None,
    AccessionNumber: str | None = None,
    StudyDate: str | None = None,
) -> list[dict[str, object]]:
    """QIDO-RS-shaped study-level query over the synthetic PACS inventory.

    Read-only, metadata-only, authenticated; mirrors DICOMweb attribute names
    so standards-aware clients can be demonstrated against the same shape.
    """
    _authorize(user)
    query = select(PacsStudy).order_by(PacsStudy.study_date.desc(), PacsStudy.id)
    if Modality:
        query = query.where(PacsStudy.modality == Modality.strip().upper())
    if PatientID:
        query = query.where(PacsStudy.patient_id == PatientID.strip())
    if AccessionNumber:
        query = query.where(PacsStudy.accession_number == AccessionNumber.strip())
    if StudyDate:
        query = query.where(PacsStudy.study_date == StudyDate.strip())
    studies = list(db.scalars(query.limit(200)))
    rows: list[dict[str, object]] = []
    for study in studies:
        row: dict[str, object] = {
            "0020000D": study.study_instance_uid,
            "00080050": study.accession_number,
            "00200010": f"STU-{study.accession_number}",
            "00100020": study.patient_id,
            "00100010": study.patient_name or "",
            "00080060": study.modality or "",
            "00080020": study.study_date or "",
            "00081030": study.study_description or "",
            "00201206": study.series_count,
            "00201208": study.instance_count,
            "00081190": f"/imaging/studies/{study.id}",
        }
        rows.append(row)
    return rows
