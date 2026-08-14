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


def _locked_report(session: Session, report_id: uuid.UUID) -> RadiologyReport | None:
    return session.scalar(
        select(RadiologyReport).where(RadiologyReport.id == report_id).with_for_update()
    )


def _locked_report_for_study(session: Session, study_id: uuid.UUID) -> RadiologyReport | None:
    return session.scalar(
        select(RadiologyReport).where(RadiologyReport.study_id == study_id).with_for_update()
    )


def _normalize_authored_content(
    *, indication: str, findings: str, impression: str
) -> tuple[str, str, str]:
    normalized = (indication.strip(), findings.strip(), impression.strip())
    for field_name, value in zip(("indication", "findings", "impression"), normalized, strict=True):
        if not value:
            raise ReportWorkflowError(f"{field_name} must not be blank", status_code=422)
    return normalized


def _check_expected_version(
    report: RadiologyReport | None, expected_version_number: int | None
) -> None:
    if report is None:
        if expected_version_number is not None:
            raise ReportWorkflowError("stale report version", status_code=409)
        return
    if expected_version_number is None:
        raise ReportWorkflowError(
            "Expected current report version is required",
            status_code=409,
        )
    if report.current_version_number != expected_version_number:
        raise ReportWorkflowError("stale report version", status_code=409)


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
    expected_version_number: int | None = None,
) -> tuple[RadiologyReport, RadiologyReportVersion]:
    _ensure_study(session, study_id)
    report = _locked_report_for_study(session, study_id)
    _check_expected_version(report, expected_version_number)
    if report is None:
        report = RadiologyReport(study_id=study_id, status=ReportStatus.DRAFT)
        session.add(report)
        session.flush()
    elif report.status != ReportStatus.DRAFT:
        raise ReportWorkflowError(
            "A finalized report cannot be edited; create a correction instead"
        )
    indication, findings, impression = _normalize_authored_content(
        indication=indication,
        findings=findings,
        impression=impression,
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
    expected_version_number: int,
) -> tuple[RadiologyReport, RadiologyReportVersion]:
    report = _locked_report(session, report_id)
    if report is None:
        raise ReportWorkflowError("Report not found", status_code=404)
    _check_expected_version(report, expected_version_number)
    _ensure_study(session, report.study_id)
    if report.status != ReportStatus.FINALIZED:
        raise ReportWorkflowError("Only a finalized report can enter correction")
    indication, findings, impression = _normalize_authored_content(
        indication=indication,
        findings=findings,
        impression=impression,
    )
    correction_reason = correction_reason.strip()
    if not correction_reason:
        raise ReportWorkflowError("correction_reason must not be blank", status_code=422)
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
    expected_version_number: int,
) -> tuple[RadiologyReport, RadiologyReportVersion]:
    report = _locked_report(session, report_id)
    if report is None:
        raise ReportWorkflowError("Report not found", status_code=404)
    _check_expected_version(report, expected_version_number)
    _ensure_study(session, report.study_id)
    if report.status not in {ReportStatus.DRAFT, ReportStatus.CORRECTION_PENDING}:
        raise ReportWorkflowError("Only a draft or pending correction can be finalized")
    source = _latest_version(session, report)
    if source is None:
        raise ReportWorkflowError("A report requires authored content before finalization")
    indication, findings, impression = _normalize_authored_content(
        indication=source.indication,
        findings=source.findings,
        impression=source.impression,
    )
    version = RadiologyReportVersion(
        report_id=report.id,
        version_number=_next_version_number(session, report),
        kind=ReportVersionKind.FINAL,
        author_id=author_id,
        indication=indication,
        findings=findings,
        impression=impression,
        correction_reason=source.correction_reason.strip()
        if source.correction_reason is not None
        else None,
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
