"""report share allowlist: expiring, audited, revocable report sharing

Revision ID: 0018_report_share_allowlist
Revises: 0017_incident_proposal_superseded
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_report_share_allowlist"
down_revision: str | None = "0017_incident_proposal_superseded"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radiology_report_shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("radiology_reports.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "study_id",
            sa.Uuid(),
            sa.ForeignKey("pacs_studies.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("recipient_label", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_radiology_report_share_status",
        ),
        sa.UniqueConstraint(
            "report_id",
            "recipient_label",
            name="uq_radiology_report_share_recipient",
        ),
    )


def downgrade() -> None:
    op.drop_table("radiology_report_shares")
