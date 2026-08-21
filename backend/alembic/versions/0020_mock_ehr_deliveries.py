"""mock EHR receiver inbox: delivery evidence for finalized reports

Revision ID: 0020_mock_ehr_deliveries
Revises: 0019_procedure_steps
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_mock_ehr_deliveries"
down_revision: str | None = "0019_procedure_steps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mock_ehr_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("radiology_reports.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "study_id",
            sa.Uuid(),
            sa.ForeignKey("pacs_studies.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("receiver", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("received_by", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('received')",
            name="ck_mock_ehr_delivery_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("mock_ehr_deliveries")
