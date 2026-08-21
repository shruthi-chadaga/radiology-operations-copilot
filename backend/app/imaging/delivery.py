"""Email delivery of share links via the local synthetic MailHog SMTP relay.

Emailing a share rotates its token: a fresh raw token is generated, only its
hash is persisted, and the previous token stops resolving. The raw token
travels solely inside the one email message and is never logged or audited.
"""

import secrets
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.config import get_settings
from app.imaging.models import (
    RadiologyReport,
    RadiologyReportShare,
    RadiologyReportShareStatus,
    ReportStatus,
)


class ShareDeliveryError(Exception):
    """Expected share delivery failure."""

    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def rotate_and_send_share_link(
    session: Session,
    *,
    share: "RadiologyReportShare",
    recipient_email: str,
) -> str:
    """Rotate the share token, send exactly one message, return the new raw token.

    The caller is responsible for auditing with ``raw_token_stored: false`` and
    for committing.
    """
    if isinstance(share.status, RadiologyReportShareStatus):
        current_status = share.status
    else:
        current_status = RadiologyReportShareStatus(share.status)
    if current_status != RadiologyReportShareStatus.ACTIVE:
        raise ShareDeliveryError("Only an active share can be emailed", status_code=409)

    report = session.get(RadiologyReport, share.report_id)
    if report is None or report.status != ReportStatus.FINALIZED:
        raise ShareDeliveryError("Only a finalized report can be shared by email", status_code=409)

    settings = get_settings()
    new_token = secrets.token_urlsafe(32)
    share.token_hash = RadiologyReportShare.hash_token(new_token)
    session.flush()

    frontend_base = settings.frontend_url.rstrip("/")
    share_id_text = str(share.id)
    link = f"{frontend_base}/share/{quote(share_id_text)}?token={quote(new_token)}"

    message = EmailMessage()
    message["From"] = f"{settings.app_name} <shares@synthetic.local>"
    message["To"] = recipient_email
    message["Subject"] = "Synthetic imaging report share link"
    message.set_content(
        "A synthetic radiology report has been shared with you.\n"
        "\n"
        f"Recipient label: {share.recipient_label}\n"
        f"Expires at: {share.expires_at.isoformat()}\n"
        "\n"
        "Open this link to view the finalized report text:\n"
        f"{link}\n"
        "\n"
        "This link expires automatically and can be revoked by the sender.\n"
        "Synthetic portfolio data only; no real patient information.\n"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(message)
    except OSError as exc:
        raise ShareDeliveryError("The share email could not be delivered", status_code=502) from exc
    return new_token
