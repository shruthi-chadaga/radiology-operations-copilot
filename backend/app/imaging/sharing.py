"""Deterministic, audited report-share allowlist operations.

Shares are allowlisted per (report, recipient label), expire mandatorily, are
revocable, and never persist raw tokens. Creating or revoking a share never
touches PACS or report content.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.imaging.models import (
    RadiologyReport,
    RadiologyReportShare,
    RadiologyReportShareStatus,
    RadiologyReportVersion,
    ReportStatus,
)

TOKEN_BYTES = 32
MAX_SHARE_TTL_HOURS = 336


class ShareWorkflowError(Exception):
    """Expected share state transition failure."""

    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _locked_report(session: Session, report_id: uuid.UUID) -> RadiologyReport:
    report = session.scalar(
        select(RadiologyReport)
        .where(RadiologyReport.id == report_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if report is None:
        raise ShareWorkflowError("Report not found", status_code=404)
    return report


def create_share(
    session: Session,
    *,
    report_id: uuid.UUID,
    created_by: str,
    recipient_label: str,
    expires_in_hours: int,
) -> tuple[RadiologyReportShare, str]:
    """Create one allowlisted share; returns (share, raw_token)."""
    if not 1 <= expires_in_hours <= MAX_SHARE_TTL_HOURS:
        raise ShareWorkflowError("expires_in_hours must be between 1 and 336", status_code=422)
    label = recipient_label.strip()
    if not label:
        raise ShareWorkflowError("recipient label must not be blank", status_code=422)
    report = _locked_report(session, report_id)
    if report.status != ReportStatus.FINALIZED:
        raise ShareWorkflowError("Only a finalized report can be shared", status_code=409)
    existing = session.scalar(
        select(RadiologyReportShare).where(
            RadiologyReportShare.report_id == report.id,
            RadiologyReportShare.recipient_label == label,
        )
    )
    if existing is not None:
        raise ShareWorkflowError(
            "An allowlist entry already exists for this recipient", status_code=409
        )
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    share = RadiologyReportShare(
        report_id=report.id,
        study_id=report.study_id,
        created_by=created_by,
        token_hash=RadiologyReportShare.hash_token(raw_token),
        recipient_label=label,
        status=RadiologyReportShareStatus.ACTIVE,
        expires_at=datetime.now(UTC) + timedelta(hours=expires_in_hours),
    )
    session.add(share)
    try:
        session.flush()
    except IntegrityError as exc:
        raise ShareWorkflowError(
            "An allowlist entry already exists for this recipient", status_code=409
        ) from exc
    return share, raw_token


def list_shares(session: Session, *, report_id: uuid.UUID) -> list[RadiologyReportShare]:
    return list(
        session.scalars(
            select(RadiologyReportShare)
            .where(RadiologyReportShare.report_id == report_id)
            .order_by(RadiologyReportShare.created_at, RadiologyReportShare.id)
        )
    )


def revoke_share(session: Session, *, share_id: uuid.UUID, revoked_by: str) -> RadiologyReportShare:
    share = session.scalar(
        select(RadiologyReportShare)
        .where(RadiologyReportShare.id == share_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if share is None:
        raise ShareWorkflowError("Share not found", status_code=404)
    current_status = (
        share.status
        if isinstance(share.status, RadiologyReportShareStatus)
        else RadiologyReportShareStatus(share.status)
    )
    if current_status == RadiologyReportShareStatus.REVOKED:
        raise ShareWorkflowError("Share has already been revoked", status_code=409)
    share.status = RadiologyReportShareStatus.REVOKED
    share.revoked_at = datetime.now(UTC)
    session.flush()
    return share


def resolve_active_share(session: Session, *, raw_token: str) -> RadiologyReportShare | None:
    """Resolve a raw token to an active, unexpired share; None otherwise."""
    if not raw_token:
        return None
    token_hash = RadiologyReportShare.hash_token(raw_token)
    share = session.scalar(
        select(RadiologyReportShare).where(RadiologyReportShare.token_hash == token_hash)
    )
    if share is None:
        return None
    current_status = (
        share.status
        if isinstance(share.status, RadiologyReportShareStatus)
        else RadiologyReportShareStatus(share.status)
    )
    if current_status != RadiologyReportShareStatus.ACTIVE:
        return None
    expires_at = share.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    report = session.get(RadiologyReport, share.report_id)
    if report is None or report.status != ReportStatus.FINALIZED:
        # A non-finalized (e.g. correction pending) report is not shared.
        return None
    return share


def shared_report_payload(session: Session, share: RadiologyReportShare) -> dict[str, str]:
    """Bounded recipient-facing payload; no patient identifiers beyond the label."""
    report = session.get(RadiologyReport, share.report_id)
    versions = list(
        session.scalars(
            select(RadiologyReportVersion)
            .where(RadiologyReportVersion.report_id == share.report_id)
            .order_by(RadiologyReportVersion.version_number)
        )
    )
    current_version_number = report.current_version_number if report is not None else None
    current = next(
        (
            version
            for version in reversed(versions)
            if version.version_number == current_version_number
        ),
        None,
    )
    return {
        "report_id": str(share.report_id),
        "recipient_label": share.recipient_label,
        "status": ReportStatus.FINALIZED.value,
        "version": str(current_version_number or ""),
        "indication": current.indication if current else "",
        "findings": current.findings if current else "",
        "impression": current.impression if current else "",
        "expires_at": share.expires_at.isoformat(),
    }
