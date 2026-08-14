"""PACS/RIS APIs expose metadata and allowlisted transfers only."""

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import Role, User
from app.db.session import get_db
from app.pacs.adapter import PacsAdapter
from app.pacs.dependencies import get_pacs_adapters
from app.pacs.dispatch import publish_pending_transfer_dispatches
from app.pacs.inventory import UnsafePacsMetadata, check_node_health, sync_inventory
from app.pacs.models import (
    PacsHealthCheck,
    PacsNode,
    PacsStudy,
    ReconciliationResult,
    TransferAttempt,
    TransferJob,
)
from app.pacs.schemas import (
    DicomTagItem,
    DicomTagsResponse,
    HealthCheckResponse,
    InventorySyncRequest,
    InventorySyncResponse,
    PacsDashboardResponse,
    PacsNodePage,
    PacsNodeResponse,
    PacsStudyPage,
    PacsStudyResponse,
    ReconciliationResponse,
    SeriesInstanceRef,
    SeriesItem,
    SeriesListResponse,
    TransferAttemptResponse,
    TransferCreateRequest,
    TransferDetailResponse,
    TransferPage,
    TransferResponse,
)
from app.pacs.transfer import (
    TransferConflict,
    TransferCreate,
    create_transfer,
    reconcile_transfer,
)
from app.workers.pacs_tasks import execute_transfer_task

router = APIRouter(prefix="/pacs", tags=["pacs-ris"])
_WRITE_ROLES = {Role.PACS_ADMIN, Role.OPERATIONS_MANAGER}
_READ_ROLES = _WRITE_ROLES | {Role.AUDITOR}


def _authorize(user: User, *, write: bool) -> None:
    roles = _WRITE_ROLES if write else _READ_ROLES
    if user.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def _audit_transfer_denial(
    db: Session,
    *,
    actor_id: str,
    payload: TransferCreateRequest,
    request_id: str,
    correlation_id: str,
    error_code: str,
    error_message: str,
) -> None:
    append_audit_event(
        db,
        actor=AuditActor("user", actor_id),
        action="pacs.transfer.request_denied",
        entity_type="pacs_study",
        entity_id=payload.study_id,
        decision_reason="Deterministic PACS transfer policy denied the request",
        correlation_id=correlation_id,
        request_id=request_id,
        success=False,
        policy_version="pacs-transfer-policy-v1",
        after_state={
            "source_node_id": payload.source_node_id,
            "destination_node_id": payload.destination_node_id,
        },
        error_code=error_code,
        error_message=error_message,
    )
    db.commit()


def _node_response(node: PacsNode) -> PacsNodeResponse:
    return PacsNodeResponse(
        id=str(node.id),
        name=node.name,
        node_type=node.node_type,
        dicom_ae_title=node.dicom_ae_title,
        active=node.active,
        last_health_status=node.last_health_status,
        last_health_at=node.last_health_at,
    )


def _study_response(study: PacsStudy) -> PacsStudyResponse:
    return PacsStudyResponse(
        id=str(study.id),
        node_id=str(study.node_id),
        study_instance_uid=study.study_instance_uid,
        accession_number=study.accession_number,
        patient_id=study.patient_id,
        patient_name=study.patient_name,
        patient_birth_date=study.patient_birth_date,
        patient_sex=study.patient_sex,
        study_date=study.study_date,
        study_description=study.study_description,
        modality=study.modality,
        series_count=study.series_count,
        instance_count=study.instance_count,
    )


def _transfer_response(job: TransferJob) -> TransferResponse:
    return TransferResponse(
        id=str(job.id),
        source_node_id=str(job.source_node_id),
        destination_node_id=str(job.destination_node_id),
        study_id=str(job.study_id),
        status=job.status.value,
        retry_count=job.retry_count,
        maximum_retries=job.maximum_retries,
        correlation_id=job.correlation_id,
    )


def _adapter_for(node: PacsNode, adapters: dict[str, PacsAdapter]) -> PacsAdapter:
    adapter = adapters.get(node.adapter_key)
    if adapter is None:
        raise HTTPException(status_code=503, detail="PACS adapter unavailable")
    return adapter


@router.get("/nodes", response_model=PacsNodePage)
def list_nodes(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PacsNodePage:
    _authorize(user, write=False)
    nodes = db.scalars(select(PacsNode).order_by(PacsNode.name))
    return PacsNodePage(items=[_node_response(node) for node in nodes])


@router.post("/nodes/{node_id}/health-check", response_model=HealthCheckResponse)
def health_check(
    node_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> HealthCheckResponse:
    _authorize(user, write=True)
    node = db.get(PacsNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="PACS node not found")
    check = check_node_health(db, node, _adapter_for(node, adapters), actor_id=str(user.id))
    db.commit()
    return HealthCheckResponse(
        id=str(check.id),
        node_id=str(check.node_id),
        status=check.status,
        latency_ms=check.latency_ms,
        checked_at=check.checked_at,
    )


@router.get("/nodes/{node_id}/health", response_model=HealthCheckResponse)
def latest_health(
    node_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HealthCheckResponse:
    _authorize(user, write=False)
    check = db.scalar(
        select(PacsHealthCheck)
        .where(PacsHealthCheck.node_id == node_id)
        .order_by(PacsHealthCheck.checked_at.desc())
        .limit(1)
    )
    if check is None:
        raise HTTPException(status_code=404, detail="PACS health evidence not found")
    return HealthCheckResponse(
        id=str(check.id),
        node_id=str(check.node_id),
        status=check.status,
        latency_ms=check.latency_ms,
        checked_at=check.checked_at,
    )


@router.post("/studies/sync", response_model=InventorySyncResponse)
def synchronize_studies(
    payload: InventorySyncRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> InventorySyncResponse:
    _authorize(user, write=True)
    try:
        node_id = uuid.UUID(payload.node_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid PACS node ID") from exc
    node = db.get(PacsNode, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="PACS node not found")
    request_id = request.headers.get("x-request-id", f"local-{uuid.uuid4().hex[:12]}")
    correlation_id = request.headers.get("x-correlation-id", request_id)
    try:
        study_count = sync_inventory(db, node, _adapter_for(node, adapters), actor_id=str(user.id))
        db.commit()
    except UnsafePacsMetadata as exc:
        db.rollback()
        append_audit_event(
            db,
            actor=AuditActor("user", str(user.id)),
            action="pacs.inventory.synchronization_denied",
            entity_type="pacs_node",
            entity_id=str(node.id),
            decision_reason="PACS metadata failed deterministic synthetic-only validation",
            correlation_id=correlation_id,
            request_id=request_id,
            success=False,
            policy_version="synthetic-pacs-metadata-v1",
            error_code="UNSAFE_PACS_METADATA",
            error_message=str(exc),
        )
        db.commit()
        raise HTTPException(status_code=409, detail="PACS metadata is not synthetic-only") from exc
    return InventorySyncResponse(node_id=str(node.id), study_count=study_count)


@router.get("/studies", response_model=PacsStudyPage)
def list_studies(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PacsStudyPage:
    _authorize(user, write=False)
    studies = db.scalars(select(PacsStudy).order_by(PacsStudy.last_seen_at.desc()).limit(200))
    return PacsStudyPage(items=[_study_response(study) for study in studies])


@router.get("/studies/{study_id}", response_model=PacsStudyResponse)
def get_study(
    study_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PacsStudyResponse:
    _authorize(user, write=False)
    study = db.get(PacsStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="PACS study metadata not found")
    return _study_response(study)


@router.post("/transfers", response_model=TransferResponse, status_code=status.HTTP_202_ACCEPTED)
def queue_transfer(
    payload: TransferCreateRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=160)],
) -> TransferResponse:
    _authorize(user, write=True)
    actor_id = str(user.id)
    request_id = request.headers.get("x-request-id", f"local-{uuid.uuid4().hex[:12]}")
    correlation_id = request.headers.get("x-correlation-id", idempotency_key)
    try:
        job = create_transfer(
            db,
            TransferCreate(
                source_node_id=uuid.UUID(payload.source_node_id),
                destination_node_id=uuid.UUID(payload.destination_node_id),
                study_id=uuid.UUID(payload.study_id),
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                actor_id=actor_id,
            ),
        )
        db.commit()
    except (ValueError, TransferConflict) as exc:
        db.rollback()
        _audit_transfer_denial(
            db,
            actor_id=actor_id,
            payload=payload,
            request_id=request_id,
            correlation_id=correlation_id,
            error_code="TRANSFER_CONFLICT"
            if isinstance(exc, TransferConflict)
            else "INVALID_TRANSFER",
            error_message=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        existing_job = db.scalar(
            select(TransferJob).where(TransferJob.idempotency_key == idempotency_key)
        )
        if existing_job is None:
            _audit_transfer_denial(
                db,
                actor_id=actor_id,
                payload=payload,
                request_id=request_id,
                correlation_id=correlation_id,
                error_code="CONCURRENT_TRANSFER_CONFLICT",
                error_message="Concurrent transfer conflict",
            )
            raise HTTPException(status_code=409, detail="Concurrent transfer conflict") from exc
        if (
            existing_job.source_node_id != uuid.UUID(payload.source_node_id)
            or existing_job.destination_node_id != uuid.UUID(payload.destination_node_id)
            or existing_job.study_id != uuid.UUID(payload.study_id)
        ):
            _audit_transfer_denial(
                db,
                actor_id=actor_id,
                payload=payload,
                request_id=request_id,
                correlation_id=correlation_id,
                error_code="IDEMPOTENCY_KEY_REUSED",
                error_message="Idempotency key was reused for a different transfer",
            )
            raise HTTPException(
                status_code=409, detail="Idempotency key was reused for a different transfer"
            ) from exc
        job = existing_job
    publish_pending_transfer_dispatches(
        db,
        lambda transfer_id: execute_transfer_task.delay(transfer_id),
        transfer_id=job.id,
        limit=1,
    )
    db.commit()
    return _transfer_response(job)


@router.get("/transfers", response_model=TransferPage)
def list_transfers(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TransferPage:
    _authorize(user, write=False)
    jobs = db.scalars(select(TransferJob).order_by(TransferJob.created_at.desc()).limit(200))
    return TransferPage(items=[_transfer_response(job) for job in jobs])


@router.get("/transfers/{transfer_id}", response_model=TransferDetailResponse)
def get_transfer(
    transfer_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> TransferDetailResponse:
    _authorize(user, write=False)
    job = db.get(TransferJob, transfer_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    attempts = db.scalars(
        select(TransferAttempt)
        .where(TransferAttempt.transfer_job_id == transfer_id)
        .order_by(TransferAttempt.attempt_number)
    )
    reconciliations = db.scalars(
        select(ReconciliationResult)
        .where(ReconciliationResult.transfer_job_id == transfer_id)
        .order_by(ReconciliationResult.checked_at)
    )
    basic = _transfer_response(job)
    return TransferDetailResponse(
        **basic.model_dump(),
        attempts=[
            TransferAttemptResponse(
                id=str(attempt.id),
                attempt_number=attempt.attempt_number,
                outcome=attempt.outcome,
                started_at=attempt.started_at,
                completed_at=attempt.completed_at,
                redacted_error=attempt.redacted_error,
            )
            for attempt in attempts
        ],
        reconciliations=[
            ReconciliationResponse(
                id=str(result.id),
                transfer_job_id=str(result.transfer_job_id),
                outcome=result.outcome,
                identifiers_match=result.identifiers_match,
                instance_counts_match=result.instance_counts_match,
                source_instance_count=result.source_instance_count,
                destination_instance_count=result.destination_instance_count,
            )
            for result in reconciliations
        ],
    )


@router.post("/transfers/{transfer_id}/reconcile", response_model=ReconciliationResponse)
def reconcile_transfer_endpoint(
    transfer_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> ReconciliationResponse:
    _authorize(user, write=True)
    try:
        result = reconcile_transfer(
            db,
            transfer_id,
            _adapter_required(adapters, "source"),
            _adapter_required(adapters, "destination"),
            actor_id=str(user.id),
        )
        db.commit()
    except TransferConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReconciliationResponse(
        id=str(result.id),
        transfer_job_id=str(result.transfer_job_id),
        outcome=result.outcome,
        identifiers_match=result.identifiers_match,
        instance_counts_match=result.instance_counts_match,
        source_instance_count=result.source_instance_count,
        destination_instance_count=result.destination_instance_count,
    )


@router.get("/dashboard", response_model=PacsDashboardResponse)
def pacs_dashboard(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PacsDashboardResponse:
    _authorize(user, write=False)
    total_studies = db.scalar(select(func.count()).select_from(PacsStudy)) or 0
    total_nodes = db.scalar(select(func.count()).select_from(PacsNode)) or 0
    healthy = db.scalar(
        select(func.count())
        .select_from(PacsNode)
        .where(PacsNode.last_health_status == "healthy")
    ) or 0
    modalities = db.scalars(select(PacsStudy.modality).where(PacsStudy.modality.isnot(None)))
    modality_counts = dict(Counter(modalities))
    recent_window = datetime.now(UTC) - timedelta(hours=24)
    recent_studies = db.scalar(
        select(func.count())
        .select_from(PacsStudy)
        .where(PacsStudy.last_seen_at >= recent_window)
    ) or 0
    recent_transfers = db.scalar(
        select(func.count())
        .select_from(TransferJob)
        .where(TransferJob.created_at >= recent_window)
    ) or 0
    return PacsDashboardResponse(
        total_studies=total_studies,
        healthy_nodes=healthy,
        total_nodes=total_nodes,
        modality_counts=modality_counts,
        recent_study_count=recent_studies,
        recent_transfer_count=recent_transfers,
    )


_DICOM_TAG_GROUPS: dict[str, str] = {
    "StudyInstanceUID": "Study",
    "StudyDate": "Study",
    "StudyTime": "Study",
    "StudyDescription": "Study",
    "AccessionNumber": "Study",
    "StudyID": "Study",
    "Modality": "Study",
    "ReferringPhysicianName": "Study",
    "InstitutionName": "Equipment",
    "Manufacturer": "Equipment",
    "ManufacturerModelName": "Equipment",
    "PatientID": "Patient",
    "PatientName": "Patient",
    "PatientBirthDate": "Patient",
    "PatientSex": "Patient",
    "PatientAge": "Patient",
    "SeriesDescription": "Series",
    "SeriesNumber": "Series",
    "InstanceNumber": "Instance",
    "SOPInstanceUID": "Instance",
    "SeriesInstanceUID": "Series",
    "BodyPartExamined": "Study",
}

_TAG_NAMES: dict[str, str] = {
    "StudyInstanceUID": "Study Instance UID",
    "StudyDate": "Study Date",
    "StudyTime": "Study Time",
    "StudyDescription": "Study Description",
    "AccessionNumber": "Accession Number",
    "StudyID": "Study ID",
    "Modality": "Modality",
    "ReferringPhysicianName": "Referring Physician",
    "InstitutionName": "Institution",
    "Manufacturer": "Manufacturer",
    "ManufacturerModelName": "Model",
    "PatientID": "Patient ID",
    "PatientName": "Patient Name",
    "PatientBirthDate": "Birth Date",
    "PatientSex": "Sex",
    "PatientAge": "Age",
    "SeriesDescription": "Series Description",
    "SeriesNumber": "Series Number",
    "InstanceNumber": "Instance Number",
    "SOPInstanceUID": "SOP Instance UID",
    "SpecificCharacterSet": "Character Set",
    "SOPClassUID": "SOP Class UID",
    "ImageType": "Image Type",
    "SeriesInstanceUID": "Series Instance UID",
    "BodyPartExamined": "Body Part",
}


@router.get("/studies/{study_id}/tags", response_model=DicomTagsResponse)
def get_study_tags(
    study_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> DicomTagsResponse:
    _authorize(user, write=False)
    study = db.get(PacsStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="PACS study metadata not found")
    node = db.get(PacsNode, study.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="PACS node not found")
    adapter = _adapter_for(node, adapters)
    try:
        raw_tags = adapter.get_study_tags(study.orthanc_study_id)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Failed to fetch DICOM tags from Orthanc"
        ) from exc
    items: list[DicomTagItem] = []
    for source, tags_dict in raw_tags.items():
        for tag_key, tag_value in tags_dict.items():
            group = (
                "Patient"
                if source == "PatientMainDicomTags"
                else _DICOM_TAG_GROUPS.get(tag_key, "Other")
            )
            name = _TAG_NAMES.get(tag_key, tag_key)
            items.append(
                DicomTagItem(
                    tag=tag_key,
                    name=name,
                    value=tag_value,
                    group=group,
                )
            )
    return DicomTagsResponse(study_id=str(study.id), tags=items)


@router.get("/studies/{study_id}/series", response_model=SeriesListResponse)
def get_study_series(
    study_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    adapters: Annotated[dict[str, PacsAdapter], Depends(get_pacs_adapters)],
) -> SeriesListResponse:
    _authorize(user, write=False)
    study = db.get(PacsStudy, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail="PACS study metadata not found")
    node = db.get(PacsNode, study.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="PACS node not found")
    adapter = _adapter_for(node, adapters)
    try:
        raw_series = adapter.list_series(study.orthanc_study_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to fetch series from Orthanc") from exc
    items: list[SeriesItem] = []
    for raw in raw_series:
        tags_raw = raw.get("tags")
        tags_list: list[DicomTagItem] = []
        if isinstance(tags_raw, dict):
            for tk, tv in tags_raw.items():
                tags_list.append(
                    DicomTagItem(
                        tag=tk,
                        name=_TAG_NAMES.get(tk, tk),
                        value=tv if isinstance(tv, str) else str(tv),
                        group="Series",
                    )
                )
        instances_raw = raw.get("instances")
        instances: list[SeriesInstanceRef] = []
        if isinstance(instances_raw, list):
            for inst in instances_raw:
                if isinstance(inst, dict):
                    raw_instance_number = inst.get("instance_number")
                    instances.append(
                        SeriesInstanceRef(
                            orthanc_instance_id=str(inst.get("orthanc_instance_id", "")),
                            sop_instance_uid=str(inst.get("sop_instance_uid", "")),
                            instance_number=(
                                raw_instance_number
                                if isinstance(raw_instance_number, str)
                                else None
                            ),
                        )
                    )
        raw_count = raw.get("instance_count")
        count = raw_count if isinstance(raw_count, int) else 0
        raw_series_number = raw.get("series_number")
        raw_series_description = raw.get("series_description")
        items.append(
            SeriesItem(
                orthanc_series_id=str(raw.get("orthanc_series_id", "")),
                series_instance_uid=str(raw.get("series_instance_uid", "")),
                series_number=(
                    raw_series_number if isinstance(raw_series_number, str) else None
                ),
                series_description=(
                    raw_series_description
                    if isinstance(raw_series_description, str)
                    else None
                ),
                modality=raw.get("modality") if isinstance(raw.get("modality"), str) else None,
                instance_count=count,
                instances=instances,
                tags=tags_list,
            )
        )
    return SeriesListResponse(study_id=str(study.id), series=items)


def _adapter_required(adapters: dict[str, PacsAdapter], key: str) -> PacsAdapter:
    adapter = adapters.get(key)
    if adapter is None:
        raise HTTPException(status_code=503, detail=f"{key} PACS adapter unavailable")
    return adapter
