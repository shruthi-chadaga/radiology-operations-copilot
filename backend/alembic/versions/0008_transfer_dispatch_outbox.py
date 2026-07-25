"""add durable transfer dispatch outbox

Revision ID: 0008_transfer_dispatch_outbox
Revises: 0007_active_appointment_unique
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_transfer_dispatch_outbox"
down_revision: str | None = "0007_active_appointment_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transfer_dispatches",
        sa.Column("transfer_job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["transfer_job_id"], ["transfer_jobs.id"]),
        sa.PrimaryKeyConstraint("transfer_job_id"),
    )
    op.create_index(
        "ix_transfer_dispatches_status", "transfer_dispatches", ["status"], unique=False
    )
    op.execute(
        """
        INSERT INTO transfer_dispatches (
            transfer_job_id, status, attempt_count, created_at
        )
        SELECT id, 'pending', 0, CURRENT_TIMESTAMP
        FROM transfer_jobs
        WHERE status = 'PENDING'
        ON CONFLICT (transfer_job_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_transfer_dispatches_status", table_name="transfer_dispatches")
    op.drop_table("transfer_dispatches")
