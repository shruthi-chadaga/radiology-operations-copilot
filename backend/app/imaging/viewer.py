"""Deterministic, metadata-only helpers for the Phase 2 study viewer."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pacs.models import PacsStudy


def is_synthetic_study(study: PacsStudy) -> bool:
    """Require the inventory attestation before exposing a rendered preview."""
    return study.metadata_json.get("synthetic") is True


def find_prior_studies(
    session: Session,
    current: PacsStudy,
    *,
    limit: int = 3,
) -> list[PacsStudy]:
    """Find the newest earlier synthetic studies for the same patient/modality.

    Matching deliberately uses stable administrative metadata only. It does not
    compare image content or make a clinical judgment about similarity.
    """
    if not current.study_date or not is_synthetic_study(current):
        return []
    query = select(PacsStudy).where(
        PacsStudy.id != current.id,
        PacsStudy.patient_id == current.patient_id,
        PacsStudy.study_date < current.study_date,
    )
    if current.modality:
        query = query.where(PacsStudy.modality == current.modality)
    candidates = session.scalars(
        query.order_by(PacsStudy.study_date.desc(), PacsStudy.last_seen_at.desc(), PacsStudy.id)
    )
    return [study for study in candidates if is_synthetic_study(study)][:limit]


def first_instance_id(series: list[dict[str, object]]) -> str | None:
    """Select a deterministic representative instance without exposing raw IDs to UI."""
    for series_item in series:
        instances = series_item.get("instances")
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            instance_id = instance.get("orthanc_instance_id")
            if isinstance(instance_id, str) and instance_id:
                return instance_id
    return None
