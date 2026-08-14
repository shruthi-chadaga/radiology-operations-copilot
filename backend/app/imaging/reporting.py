"""User-authored synthetic report workflow with immutable versions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.imaging.models import (
    ImagingWorklistItem,
    ImagingWorklistStatus,
    RadiologyReport,
    RadiologyReportVersion,
    ReportStatus,
    ReportVersionKind,
)
from app.pacs.models import PacsStudy


class ReportWorkflowError(Exception):
    """Expected report state transition failure."""

    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def get_report(session: Session, study_id: uuid.UUID) -> RadiologyReport | None:
    study = session.get(PacsStudy, study_id)
    if study is None or (study.metadata_json or {}).get("synthetic") is not True:
        return None
    return session.scalar(select(RadiologyReport).where(RadiologyReport.study_id == study_id))


def _latest_version(session: Session, report: RadiologyReport) -> RadiologyReportVersion | None:
    return session.scalar(
        select(RadiologyReportVersion)
        .where(RadiologyReportVersion.report_id == report.id)
        .order_by(RadiologyReportVersion.version_number.desc())
    )


def _next_version_number(session: Session, report: RadiologyReport) -> int:
    latest = _latest_version(session, report)
    return (latest.version_number + 1) if latest else 1


def _update_worklist_status(session: Session, study_id: uuid.UUID, report_status: str) -> None:
    item = session.scalar(
        select(ImagingWorklistItem).where(ImagingWorklistItem.pacs_study_id == study_id)
    )
    if item is None:
        return
    item.report_status = report_status
    if report_status == "draft":
        item.workflow_status = ImagingWorklistStatus.REPORT_DRAFT
    elif report_status == "correction_pending":
        item.workflow_status = ImagingWorklistStatus.CORRECTION_PENDING
    elif report_status == "finalized":
        item.workflow_status = ImagingWorklistStatus.FINALIZED


def _ensure_study(session: Session, study_id: uuid.UUID) -> PacsStudy:
    study = session.get(PacsStudy, study_id)
    if study is None:
        raise ReportWorkflowError("PACS study metadata not found", status_code=404)
    if (study.metadata_json or {}).get("synthetic") is not True:
        raise ReportWorkflowError("Only attested synthetic studies can be reported")
    return study


def save_draft(
    session: Session,
    *,
    study_id: uuid.UUID,
    author_id: str,
    indication: str,
    findings: str,
    impression: str,
) -> tuple[RadiologyReport, RadiologyReportVersion]:
    _ensure_study(session, study_id)
    report = get_report(session, study_id)
    if report is None:
        report = RadiologyReport(study_id=study_id, status=ReportStatus.DRAFT)
        session.add(report)
        session.flush()
    elif report.status != ReportStatus.DRAFT:
        raise ReportWorkflowError(
            "A finalized report cannot be edited; create a correction instead"
        )
    version = RadiologyReportVersion(
        report_id=report.id,
        version_number=_next_version_number(session, report),
        kind=ReportVersionKind.DRAFT,
        author_id=author_id,
        indication=indication,
        findings=findings,
        impression=impression,
    )
    session.add(version)
    report.current_version_number = version.version_number
    report.updated_at = datetime.now(UTC)
    _update_worklist_status(session, study_id, "draft")
    session.flush()
    return report, version


def create_correction(
    session: Session,
    *,
    report_id: uuid.UUID,
    author_id: str,
    correction_reason: str,
    indication: str,
    findings: str,
    impression: str,
) -> tuple[RadiologyReport, RadiologyReportVersion]:
    report = session.get(RadiologyReport, report_id)
    if report is None:
        raise ReportWorkflowError("Report not found", status_code=404)
    _ensure_study(session, report.study_id)
    if report.status != ReportStatus.FINALIZED:
        raise ReportWorkflowError("Only a finalized report can enter correction")
    version = RadiologyReportVersion(
        report_id=report.id,
        version_number=_next_version_number(session, report),
        kind=ReportVersionKind.CORRECTION,
        author_id=author_id,
        indication=indication,
        findings=findings,
        impression=impression,
        correction_reason=correction_reason,
    )
    session.add(version)
    report.status = ReportStatus.CORRECTION_PENDING
    report.current_version_number = version.version_number
    report.updated_at = datetime.now(UTC)
    _update_worklist_status(session, report.study_id, "correction_pending")
    session.flush()
    return report, version


def finalize_report(
    session: Session,
    *,
    report_id: uuid.UUID,
    author_id: str,
) -> tuple[RadiologyReport, RadiologyReportVersion]:
    report = session.get(RadiologyReport, report_id)
    if report is None:
        raise ReportWorkflowError("Report not found", status_code=404)
    _ensure_study(session, report.study_id)
    if report.status not in {ReportStatus.DRAFT, ReportStatus.CORRECTION_PENDING}:
        raise ReportWorkflowError("Only a draft or pending correction can be finalized")
    source = _latest_version(session, report)
    if source is None:
        raise ReportWorkflowError("A report requires authored content before finalization")
    version = RadiologyReportVersion(
        report_id=report.id,
        version_number=_next_version_number(session, report),
        kind=ReportVersionKind.FINAL,
        author_id=author_id,
        indication=source.indication,
        findings=source.findings,
        impression=source.impression,
        correction_reason=source.correction_reason,
    )
    session.add(version)
    report.status = ReportStatus.FINALIZED
    report.current_version_number = version.version_number
    report.finalized_at = datetime.now(UTC)
    report.finalized_by = author_id
    report.updated_at = datetime.now(UTC)
    _update_worklist_status(session, report.study_id, "finalized")
    session.flush()
    return report, version
