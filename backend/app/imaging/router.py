"""Imaging Workspace APIs: worklist, patient context, viewer, and reports."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.session import get_db
from app.imaging.models import (
    ImagingPriority,
    ImagingWorklistItem,
    RadiologyReport,
    RadiologyReportShare,
    RadiologyReportShareStatus,
    RadiologyReportVersion,
)
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
    SharePage,
    ShareResponse,
    ViewerComparisonResponse,
    ViewerStudyResponse,
)
from app.imaging.service import build_timeline, synchronize_worklist
from app.imaging.sharing import (
    ShareWorkflowError,
    create_share,
    list_shares,
    revoke_share,
)
from app.imaging.viewer import find_prior_studies, first_instance_id, is_synthetic_study
from app.pacs.adapter import PacsAdapter
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.models import PacsNode, PacsStudy
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
    after_state = {
        "report_id": str(share.report_id),
        "recipient_label": share.recipient_label,
        "status": share.status.value,
        "expires_at": share.expires_at.isoformat(),
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
