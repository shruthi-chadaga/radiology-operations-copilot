"""procedure step lifecycle tracking (MPPS-lite)

Revision ID: 0019_procedure_steps
Revises: 0018_report_share_allowlist
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_procedure_steps"
down_revision: str | None = "0018_report_share_allowlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "procedure_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("accession_number", sa.String(length=64), nullable=False, index=True),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("started_by", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=300), nullable=True),
        sa.Column("performed_series_count", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'discontinued')",
            name="ck_procedure_step_status",
        ),
        sa.UniqueConstraint(
            "accession_number",
            "step_number",
            name="uq_procedure_step_number",
        ),
    )
    op.create_index("ix_procedure_steps_status", "procedure_steps", ["status"])


def downgrade() -> None:
    op.drop_index("ix_procedure_steps_status", table_name="procedure_steps")
    op.drop_table("procedure_steps")
