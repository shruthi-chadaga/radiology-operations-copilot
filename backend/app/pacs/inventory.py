"""Bounded PACS health checks and metadata-only inventory synchronization."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditActor, append_audit_event
from app.pacs.adapter import PacsAdapter
from app.pacs.models import PacsHealthCheck, PacsNode, PacsStudy
from app.pacs.schemas import PacsStudyMetadata


class UnsafePacsMetadata(ValueError):
    """Raised when Orthanc metadata is not conspicuously synthetic."""


def validate_synthetic_metadata(metadata: PacsStudyMetadata) -> None:
    description = (metadata.study_description or "").lower()
    accession = metadata.accession_number.upper()
    if (
        not metadata.patient_id.upper().startswith("SYN-")
        or ("SYN" not in accession and not accession.startswith("ACC-SP-"))
        or "synthetic" not in description
    ):
        raise UnsafePacsMetadata(
            "PACS inventory contains metadata without required synthetic markers"
        )


def check_node_health(
    session: Session, node: PacsNode, adapter: PacsAdapter, *, actor_id: str
) -> PacsHealthCheck:
    evidence = adapter.health()
    status = "healthy" if evidence.healthy else "unhealthy"
    node.last_health_status = status
    node.last_health_at = datetime.now(UTC)
    check = PacsHealthCheck(
        node_id=node.id,
        status=status,
        latency_ms=evidence.latency_ms,
        http_status=200 if evidence.healthy else None,
        evidence_json={"node_name": evidence.node_name, "version": evidence.version},
        redacted_error=evidence.error,
    )
    session.add(check)
    session.flush()
    append_audit_event(
        session,
        actor=AuditActor("user", actor_id),
        action="pacs.node.health_checked",
        entity_type="pacs_node",
        entity_id=str(node.id),
        decision_reason="Bounded non-destructive Orthanc system check",
        correlation_id=f"health-{check.id}",
        request_id=f"health-{check.id}",
        success=evidence.healthy,
        after_state={"status": status, "latency_ms": evidence.latency_ms},
        error_code=None if evidence.healthy else "NODE_UNAVAILABLE",
    )
    return check


def sync_inventory(session: Session, node: PacsNode, adapter: PacsAdapter, *, actor_id: str) -> int:
    studies = adapter.list_studies()
    for metadata in studies:
        validate_synthetic_metadata(metadata)
    now = datetime.now(UTC)
    for metadata in studies:
        study = session.scalar(
            select(PacsStudy).where(
                PacsStudy.node_id == node.id,
                PacsStudy.orthanc_study_id == metadata.orthanc_study_id,
            )
        )
        if study is None:
            study = PacsStudy(
                node_id=node.id,
                orthanc_study_id=metadata.orthanc_study_id,
                study_instance_uid=metadata.study_instance_uid,
                accession_number=metadata.accession_number,
                patient_id=metadata.patient_id,
                study_date=metadata.study_date,
                study_description=metadata.study_description,
                series_count=metadata.series_count,
                instance_count=metadata.instance_count,
                metadata_json={},
            )
            session.add(study)
        else:
            study.study_instance_uid = metadata.study_instance_uid
            study.accession_number = metadata.accession_number
            study.patient_id = metadata.patient_id
            study.study_date = metadata.study_date
            study.study_description = metadata.study_description
            study.series_count = metadata.series_count
            study.instance_count = metadata.instance_count
        study.metadata_json = {
            "study_instance_uid": metadata.study_instance_uid,
            "accession_number": metadata.accession_number,
            "patient_id": metadata.patient_id,
            "series_count": metadata.series_count,
            "instance_count": metadata.instance_count,
            "contains_pixel_data": False,
            "synthetic": True,
        }
        study.last_seen_at = now
    session.flush()
    append_audit_event(
        session,
        actor=AuditActor("user", actor_id),
        action="pacs.inventory.synchronized",
        entity_type="pacs_node",
        entity_id=str(node.id),
        decision_reason="Metadata-only Orthanc inventory synchronization",
        correlation_id=f"sync-{node.id}-{int(now.timestamp())}",
        request_id=f"sync-{node.id}-{int(now.timestamp())}",
        success=True,
        after_state={"study_count": len(studies), "pixel_data_stored": False},
    )
    return len(studies)
