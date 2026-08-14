"""add immutable synthetic radiology reports

Revision ID: 0014_radiology_reports
Revises: 0013_imaging_worklist_cancelled
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_radiology_reports"
down_revision: str | None = "0013_imaging_worklist_cancelled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radiology_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=True),
        sa.Column("finalized_by", sa.String(64), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["study_id"], ["pacs_studies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_id", name="uq_radiology_report_study"),
    )
    op.create_index(
        "ix_radiology_reports_study_id",
        "radiology_reports",
        ["study_id"],
        unique=False,
    )
    op.create_index(
        "ix_radiology_reports_status",
        "radiology_reports",
        ["status"],
        unique=False,
    )
    op.create_table(
        "radiology_report_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("author_id", sa.String(64), nullable=False),
        sa.Column("indication", sa.String(400), nullable=False),
        sa.Column("findings", sa.String(12000), nullable=False),
        sa.Column("impression", sa.String(4000), nullable=False),
        sa.Column("correction_reason", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["radiology_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id",
            "version_number",
            name="uq_radiology_report_version_number",
        ),
    )
    op.create_index(
        "ix_radiology_report_versions_report_id",
        "radiology_report_versions",
        ["report_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_radiology_report_versions_report_id", table_name="radiology_report_versions")
    op.drop_table("radiology_report_versions")
    op.drop_index("ix_radiology_reports_status", table_name="radiology_reports")
    op.drop_index("ix_radiology_reports_study_id", table_name="radiology_reports")
    op.drop_table("radiology_reports")
